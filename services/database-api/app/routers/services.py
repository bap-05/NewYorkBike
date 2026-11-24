"""Authenticated operator controls. Public data endpoints remain read-only."""
from datetime import datetime
from enum import Enum
import secrets
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AwareDatetime, BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.app.dependencies import require_schema
from shared.database import service_session
from shared.models import ServiceRun
from shared.time import utcnow

router = APIRouter(prefix="/api/services", tags=["Service activation"])
bearer = HTTPBearer(auto_error=False)


def authorize(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    token = request.app.state.options.service_token
    if not token:
        raise HTTPException(503, "Set API_SERVICE_TOKEN to enable service activation")
    if credentials is None or credentials.scheme.lower() != "bearer" or not secrets.compare_digest(credentials.credentials, token):
        raise HTTPException(401, "Invalid service token", headers={"WWW-Authenticate": "Bearer"})


class Service(str, Enum):
    analysis = "analysis"
    prediction = "prediction"
    clustering = "clustering"
    day_ahead = "day-ahead"
    eda = "eda"


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {"rebuild": False}})
    rebuild: bool = False
    cutoff: AwareDatetime | None = None


class JobView(BaseModel):
    job_id: int
    service: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    result: dict
    error: str | None


def view(job):
    return JobView(job_id=job.id, service=job.configuration["service"], status=job.status,
        started_at=job.started_at, finished_at=job.finished_at,
        result=job.summary or {}, error=job.error_summary)


def execute_job(app, job_id, service, body, model):
    engine, settings = app.state.job_engine, app.state.settings
    result, error, status = {}, None, "failed"
    try:
        # Same lock as the CLI/scheduler: API must not race independent workers.
        lock_name = "prediction" if service == "day-ahead" else service
        with service_session(engine, lock_name) as session:
            if service == "analysis":
                from analysis.config import AnalysisOptions
                from analysis.worker import analyze_once
                run = analyze_once(session, settings, AnalysisOptions.load(), cutoff=body.cutoff, rebuild=body.rebuild)
                result = {"service_run_id": run.id, "result_count": run.result_count, "summary": run.summary}
            elif service == "eda":
                from eda.snapshots import publish_once
                run = publish_once(session, settings, cutoff=body.cutoff, rebuild=body.rebuild)
                result = {"service_run_id": run.id, "result_count": run.result_count,
                    "summary": run.summary, "trained": False}
            elif service == "prediction":
                from prediction.config import PredictionOptions
                from prediction.worker import predict_once
                run = predict_once(session, settings, PredictionOptions.load(), rebuild=body.rebuild)
                result = {"service_run_id": run.id, "result_count": run.result_count, "summary": run.summary, "trained": False}
            elif service == "day-ahead":
                from prediction.day_ahead import publish_once, evaluate_pending
                # Same publication and evaluation policy as the independent CLI.
                # Rebuild can append an improved partial report, never replace
                # a complete publication or invent a past issuance timestamp.
                run = publish_once(session, settings, repair=body.rebuild)
                evaluation = evaluate_pending(session, settings)
                result = {"publication_id": run.id if run else None,
                    "result_count": run.result_count if run else 0, "trained": False,
                    "persisted": run is not None, "evaluation": evaluation}
                if run is None:
                    result.update(reason="no_eligible_forecast_inputs", available_hours=0)
                else:
                    report = run.summary["report"]
                    result.update(service_run_id=run.id, target_date=report["target_date"],
                        issued_at=report["issued_at"],
                        supersedes_publication_id=report.get("supersedes_publication_id"),
                        available_hours=sum(hour["status"] == "available"
                            and hour["predicted_mean_bikes"] is not None
                            for station in report["day_ahead"] for hour in station["hourly_forecasts"]))
            else:
                from clustering.config import ClusteringOptions
                from clustering.worker import cluster_once
                run = cluster_once(session, settings, ClusteringOptions.load(),
                    cutoff=body.cutoff, model=model, rebuild=body.rebuild)
                result = {"clustering_run_id": run.id, "clustering_status": run.status,
                    "model_id": model["model_id"], "model_reused": True, "trained": False,
                    "eligible_stations": run.summary["eligible_stations"],
                    "reason": run.parameters.get("reason"), "selected_k": run.parameters.get("selected_k")}
            status = "skipped" if run is None or run.status in ("skipped", "insufficient_data") else run.status
        if service == "analysis":
            from eda.snapshots import publish_once
            with service_session(engine, "eda") as session:
                snapshots = publish_once(session, settings, cutoff=body.cutoff, rebuild=body.rebuild)
                result['eda'] = {"service_run_id": snapshots.id, "status": snapshots.status,
                    "result_count": snapshots.result_count}
                result['analysis_result_count'] = result['result_count']
                result['result_count'] += snapshots.result_count
                if snapshots.status == 'success':
                    status = 'success'
    except RuntimeError:
        error = "Service busy or unavailable; retry after the current worker finishes"
    except Exception:
        error = "Service execution failed; check configuration and input data"
    with Session(engine) as session:
        job = session.get(ServiceRun, job_id)
        job.status, job.summary, job.error_summary = status, result, error
        job.finished_at = job.heartbeat_at = utcnow()
        job.result_count = result.get("result_count", result.get("eligible_stations", 0))
        session.commit()


@router.get("/clustering/model", dependencies=[Depends(authorize)])
def clustering_model(request: Request):
    from clustering.saved_model import load_model
    try:
        model = load_model(source=request.app.state.settings.bike_source)
    except (OSError, ValueError, KeyError):
        raise HTTPException(409, "Export a compatible saved clustering model first") from None
    return {key: model[key] for key in ("model_id", "source", "training_run_id", "trained_at",
        "training_window_start", "training_window_end", "selected_k", "feature_names")}


@router.post("/{service}/run", status_code=202, response_model=JobView, dependencies=[Depends(authorize)])
def activate(service: Service, body: RunRequest, request: Request, tasks: BackgroundTasks):
    if body.cutoff is not None and (service not in (Service.analysis, Service.clustering, Service.eda) or body.cutoff > utcnow()):
        raise HTTPException(422, "Cutoff must be in the past and is only supported for analysis, clustering or EDA")
    model = None
    if service == Service.clustering:
        from clustering.saved_model import load_model
        try:
            model = load_model(source=request.app.state.settings.bike_source)
        except (OSError, ValueError, KeyError):
            raise HTTPException(409, "Export a compatible saved clustering model first; API never trains") from None
    engine = request.app.state.job_engine
    with engine.connect() as connection:
        require_schema(connection, request.app)
    now = utcnow()
    with Session(engine) as session:
        job = ServiceRun(source=request.app.state.settings.bike_source, service_name="api_" + service.value,
            scheduled_at=now, started_at=now, heartbeat_at=now, status="running", attempt_count=1,
            calculation_version="api-activation-v1", configuration_hash=uuid.uuid4().hex,
            configuration={"service": service.value, **body.model_dump(mode="json")},
            summary={"phase": "queued"}, result_count=0)
        session.add(job)
        session.commit()
        response = view(job)
    tasks.add_task(execute_job, request.app, response.job_id, service.value, body, model)
    return response


@router.get("/jobs/{job_id}", response_model=JobView, dependencies=[Depends(authorize)])
def job_status(job_id: int, request: Request):
    with Session(request.app.state.job_engine) as session:
        job = session.get(ServiceRun, job_id)
        if job is None or job.source != request.app.state.settings.bike_source or not job.service_name.startswith("api_"):
            raise HTTPException(404, "Service job not found")
        return view(job)
