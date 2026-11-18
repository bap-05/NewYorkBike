"""Reuse a real test fit, then prohibit fitting and restore deleted DB outputs."""
from copy import deepcopy

import pytest
from sqlalchemy import delete, func, select

from clustering import worker
from clustering.config import ClusteringOptions
from clustering.saved_model import export_model, load_model, validate_model
from shared.models import ClusteringRun, ServiceRun, StationCluster
from test_clustering import CUTOFF, cluster_settings, populate


def test_saved_model_roundtrip_inference_and_rebuild(session, cluster_settings, tmp_path, monkeypatch):
    populate(session)
    options = ClusteringOptions()
    trained = worker.cluster_once(session, cluster_settings, options, cutoff=CUTOFF)
    expected = {row.station_id: row.cluster_label for row in session.scalars(select(StationCluster))}
    path = tmp_path / "model.json"
    artifact = export_model(session, cluster_settings.bike_source, path)
    before = path.read_bytes()
    model = load_model(path, source=cluster_settings.bike_source)
    assert model == artifact

    def forbidden(*args, **kwargs):
        pytest.fail("Inference must not fit any model")

    monkeypatch.setattr(worker, "fit_clusters", forbidden)
    monkeypatch.setattr("sklearn.preprocessing.StandardScaler.fit", forbidden)
    monkeypatch.setattr("sklearn.cluster.KMeans.fit", forbidden)
    inferred = worker.cluster_once(session, cluster_settings, options, cutoff=CUTOFF, model=model)
    assert inferred.id != trained.id
    assert inferred.parameters["trained"] is False
    assert inferred.parameters["model_id"] == artifact["model_id"]
    query = select(StationCluster).where(StationCluster.clustering_run_id == inferred.id)
    assert {row.station_id: row.cluster_label for row in session.scalars(query)} == expected
    session.execute(delete(StationCluster).where(StationCluster.clustering_run_id == inferred.id,
        StationCluster.station_id.in_(["TEST-0", "TEST-1"])))
    session.commit()
    repeat = worker.cluster_once(session, cluster_settings, options, cutoff=CUTOFF, model=model, rebuild=True)
    assert repeat.id == inferred.id
    assert len(list(session.scalars(query))) == 6
    assert session.scalar(select(func.count()).select_from(StationCluster)) == 12
    assert path.read_bytes() == before
    # Demo may remove the training run as well: inference depends on the file,
    # not the old result rows. Silver and station metadata remain untouched.
    session.execute(delete(StationCluster))
    session.execute(delete(ClusteringRun))
    session.execute(delete(ServiceRun))
    session.commit()
    restored = worker.cluster_once(session, cluster_settings, options, cutoff=CUTOFF, model=load_model(path))
    assert restored.status == "success"
    assert session.scalar(select(func.count()).select_from(StationCluster)) == 6
    assert restored.parameters["model_id"] == artifact["model_id"]
    assert path.read_bytes() == before


def test_corrupt_or_wrong_source_model_is_rejected(session, cluster_settings, tmp_path):
    populate(session)
    worker.cluster_once(session, cluster_settings, ClusteringOptions(), cutoff=CUTOFF)
    model = export_model(session, cluster_settings.bike_source, tmp_path / "model.json")
    bad = deepcopy(model)
    bad["scaler_scale"][0] = 0
    with pytest.raises(ValueError):
        validate_model(bad)
    bad = deepcopy(model)
    bad["centers_standardized"][0][0] += 1
    with pytest.raises(ValueError):
        validate_model(bad)
    with pytest.raises(ValueError):
        validate_model(model, "another-source")
