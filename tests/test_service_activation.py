"""Authenticated Swagger controls exercised against isolated SQLite only."""
from contextlib import contextmanager
from dataclasses import replace

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.routers import services
from clustering.config import ClusteringOptions
from clustering.saved_model import export_model
from clustering import worker
from shared.models import ModelVersion, ServiceRun, StationCluster
from test_api import api
from test_clustering import CUTOFF, populate

TOKEN = "unit-test-operator-token"
HEADERS = {"Authorization": "Bearer " + TOKEN}


def setup_control(app, monkeypatch):
    app.state.options = replace(app.state.options, service_token=TOKEN)
    app.state.settings = replace(app.state.settings, station_ids=())

    @contextmanager
    def isolated_session(engine, service):
        with Session(engine, expire_on_commit=False) as session:
            yield session

    monkeypatch.setattr(services, "service_session", isolated_session)


def test_controls_disabled_or_unauthorized_and_cutoff_validation(api, monkeypatch):
    client, session, app = api
    assert client.post("/api/services/analysis/run", json={}).status_code == 503
    setup_control(app, monkeypatch)
    assert client.post("/api/services/analysis/run", json={}).status_code == 401
    assert client.get("/api/services/jobs/1", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/api/services/prediction/run", json={"cutoff": CUTOFF.isoformat()}, headers=HEADERS).status_code == 422
    assert client.post("/api/services/day-ahead/run", json={"cutoff": CUTOFF.isoformat()}, headers=HEADERS).status_code == 422
    assert client.post("/api/services/analysis/run", json={"cutoff": "2026-01-01"}, headers=HEADERS).status_code == 422
    assert client.post("/api/services/training/run", json={}, headers=HEADERS).status_code == 422


def test_eda_activation_publishes_cached_charts_without_training(api, monkeypatch):
    from eda import snapshots
    client, session, app = api
    setup_control(app, monkeypatch)
    populate(session, station_count=3, days=21)
    monkeypatch.setattr(snapshots, 'utcnow', lambda: CUTOFF)
    response = client.post('/api/services/eda/run', json={'cutoff': CUTOFF.isoformat()}, headers=HEADERS)
    assert response.status_code == 202, response.text
    job = client.get(f'/api/services/jobs/{response.json()["job_id"]}', headers=HEADERS).json()
    assert job['status'] == 'success' and job['result']['trained'] is False
    assert job['result']['result_count'] == 27
    data = client.get('/api/eda/chart-data?kind=decomposition&station_id=TEST-0').json()
    assert data['storage'] == 'precomputed' and data['decomposition']


def test_api_clustering_reuses_and_restores_without_training(api, monkeypatch, tmp_path):
    client, session, app = api
    setup_control(app, monkeypatch)
    populate(session)
    options = ClusteringOptions()
    trained = worker.cluster_once(session, app.state.settings, options, cutoff=CUTOFF)
    path = tmp_path / "model.json"
    model = export_model(session, app.state.settings.bike_source, path)
    monkeypatch.setenv("CLUSTERING_MODEL_FILE", str(path))
    monkeypatch.setattr(ClusteringOptions, "load", classmethod(lambda cls: options))

    def forbidden(*args, **kwargs):
        raise AssertionError("No training allowed")

    monkeypatch.setattr("sklearn.cluster.KMeans.fit", forbidden)
    monkeypatch.setattr("sklearn.preprocessing.StandardScaler.fit", forbidden)
    assert client.get("/api/services/clustering/model", headers=HEADERS).json()["model_id"] == model["model_id"]
    body = {"cutoff": CUTOFF.isoformat(), "rebuild": True}
    response = client.post("/api/services/clustering/run", json=body, headers=HEADERS)
    assert response.status_code == 202, response.text
    job = client.get(f'/api/services/jobs/{response.json()["job_id"]}', headers=HEADERS).json()
    assert job["status"] == "success", job
    assert job["result"]["trained"] is False
    run_id = job["result"]["clustering_run_id"]
    assert run_id != trained.id
    session.execute(delete(StationCluster).where(StationCluster.clustering_run_id == run_id))
    session.commit()
    response = client.post("/api/services/clustering/run", json=body, headers=HEADERS)
    job = client.get(f'/api/services/jobs/{response.json()["job_id"]}', headers=HEADERS).json()
    assert job["status"] == "success", job
    assert len(list(session.scalars(select(StationCluster).where(StationCluster.clustering_run_id == run_id)))) == 6


def test_missing_model_is_not_silently_trained(api, monkeypatch, tmp_path):
    client, session, app = api
    setup_control(app, monkeypatch)
    monkeypatch.setenv("CLUSTERING_MODEL_FILE", str(tmp_path / "missing.json"))
    assert client.post("/api/services/clustering/run", json={}, headers=HEADERS).status_code == 409


def test_analysis_prediction_activation_and_safe_busy_status(api, monkeypatch):
    client, session, app = api
    setup_control(app, monkeypatch)
    for service in ("analysis", "prediction"):
        response = client.post(f"/api/services/{service}/run", json={"rebuild": True}, headers=HEADERS)
        assert response.status_code == 202, response.text
        job = client.get(f'/api/services/jobs/{response.json()["job_id"]}', headers=HEADERS).json()
        assert job["status"] in ("success", "skipped"), job

    @contextmanager
    def busy(*args):
        raise RuntimeError("credentials-must-not-leak")
        yield

    monkeypatch.setattr(services, "service_session", busy)
    response = client.post("/api/services/analysis/run", json={}, headers=HEADERS)
    job = client.get(f'/api/services/jobs/{response.json()["job_id"]}', headers=HEADERS)
    assert job.json()["status"] == "failed"
    assert "credentials-must-not-leak" not in job.text


def prepare_day_ahead(app, monkeypatch):
    from analysis.config import AnalysisOptions
    from prediction import day_ahead
    from test_api import NOW
    from test_day_ahead_live import report

    setup_control(app, monkeypatch)
    monkeypatch.setattr(day_ahead, "utcnow", lambda: NOW)
    monkeypatch.setattr(day_ahead.AnalysisOptions, "load", lambda: AnalysisOptions(expected_interval_seconds=300))
    monkeypatch.setattr(day_ahead, "build_report", lambda session, settings, cutoff, options: report(cutoff))
    return day_ahead


def run_day_ahead(client, body=None):
    response = client.post("/api/services/day-ahead/run", json=body or {}, headers=HEADERS)
    assert response.status_code == 202, response.text
    return client.get(f'/api/services/jobs/{response.json()["job_id"]}', headers=HEADERS).json()


def test_day_ahead_activation_publishes_scores_and_reuses_complete_report(api, monkeypatch):
    from copy import deepcopy
    from contextlib import contextmanager
    from sqlalchemy import func

    client, session, app = api
    day_ahead = prepare_day_ahead(app, monkeypatch)
    assert client.post("/api/services/day-ahead/run", json={}).status_code == 401
    assert client.get("/api/eda/day-ahead").json()["item"] is None
    locks = []
    original_session = services.service_session

    @contextmanager
    def lock_spy(engine, service):
        locks.append(service)
        with original_session(engine, service) as worker_session:
            yield worker_session

    monkeypatch.setattr(services, "service_session", lock_spy)

    def forbidden(*args, **kwargs):
        raise AssertionError("Activation must never train a new model")

    monkeypatch.setattr("prediction.training.train_once", forbidden)
    job = run_day_ahead(client)
    assert job["status"] == "success", job
    result = job["result"]
    assert result["persisted"] and result["trained"] is False
    assert result["result_count"] == result["available_hours"] == 24
    assert result["evaluation"] == {"updated_publications": 0, "newly_scored_hours": 0}
    stored = session.get(ServiceRun, result["publication_id"])
    original = deepcopy(stored.summary["report"])
    read = client.get("/api/eda/day-ahead").json()["item"]
    assert read["publication_id"] == result["publication_id"]
    assert read["day_ahead"][0]["hourly_forecasts"][0]["predicted_mean_bikes"] == 5
    monkeypatch.setattr(day_ahead, "build_report", forbidden)
    repeat = run_day_ahead(client, {"rebuild": True})
    assert repeat["status"] == "success"
    assert repeat["result"]["publication_id"] == result["publication_id"]
    session.refresh(stored)
    assert stored.summary["report"] == original
    assert locks == ["prediction", "prediction"]
    assert session.scalar(select(func.count()).select_from(ModelVersion)) == 0


def test_day_ahead_activation_restores_deleted_publication(api, monkeypatch):
    client, session, app = api
    prepare_day_ahead(app, monkeypatch)
    first = run_day_ahead(client)
    assert first["status"] == "success"
    session.execute(delete(ServiceRun).where(ServiceRun.service_name == "day_ahead"))
    session.commit()
    assert client.get("/api/eda/day-ahead").json()["item"] is None
    restored = run_day_ahead(client, {"rebuild": True})
    assert restored["status"] == "success", restored
    assert restored["result"]["persisted"]
    assert restored["result"]["publication_id"] != first["result"]["publication_id"]
    assert client.get("/api/eda/day-ahead").json()["item"]["publication_id"] == restored["result"]["publication_id"]


def test_day_ahead_insufficient_inputs_skip_and_allow_retry(api, monkeypatch):
    from test_day_ahead_live import report
    client, session, app = api
    day_ahead = prepare_day_ahead(app, monkeypatch)

    def empty_report(session, settings, cutoff, options):
        item = report(cutoff)
        for hour in item["day_ahead"][0]["hourly_forecasts"]:
            hour.update(status="insufficient_data", predicted_mean_bikes=None)
        return item

    monkeypatch.setattr(day_ahead, "build_report", empty_report)
    job = run_day_ahead(client)
    assert job["status"] == "skipped", job
    assert job["result"]["reason"] == "no_eligible_forecast_inputs"
    assert job["result"]["available_hours"] == 0
    assert job["result"]["publication_id"] is None
    assert client.get("/api/eda/day-ahead").json()["item"] is None
    monkeypatch.setattr(day_ahead, "build_report", lambda session, settings, cutoff, options: report(cutoff))
    assert run_day_ahead(client)["status"] == "success"
