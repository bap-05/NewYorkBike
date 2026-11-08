"""Explicit training job; never invoked from the five-minute prediction loop."""
from datetime import datetime

from sqlalchemy import select

from prediction.data import load_history
from prediction.learning import build_report
from prediction.registry import feature_policy, model_digest
from shared.models import ModelVersion, TrainingJob
from shared.time import utcnow


def train_once(session,settings,options):
    cutoff = utcnow()
    # The caller holds a training-specific MySQL lock, separate from prediction.
    for abandoned in session.scalars(select(TrainingJob).where(TrainingJob.source==settings.bike_source,TrainingJob.status=="running")):
        abandoned.status,abandoned.finished_at,abandoned.error_summary = "failed",cutoff,"Interrupted before publication"
    job = TrainingJob(source=settings.bike_source,requested_at=cutoff,started_at=cutoff,status="running",
        parameters={**options.as_dict(),"station_ids":sorted(settings.station_ids),"policy":feature_policy(settings,options)})
    session.add(job)
    session.commit()
    job_id = job.id
    try:
        stations,groups = load_history(session,settings,cutoff,options)
        report,artifact = build_report(stations,groups,settings,options)
        job.summary,job.status = report,report["status"]
        if artifact is not None:
            digest = model_digest(report,artifact,settings,options)
            model = session.scalar(select(ModelVersion).where(ModelVersion.source==settings.bike_source,ModelVersion.identity_hash==digest))
            if model is None:
                created = utcnow()
                model = ModelVersion(source=settings.bike_source,name="Random Forest availability +30m",kind="random_forest",
                    identity_hash=digest,created_at=created,trained_at=created,
                    train_start=datetime.fromisoformat(report["production_training_range"]["start"]),
                    train_end=datetime.fromisoformat(report["production_training_range"]["end"]),
                    feature_config={"policy":feature_policy(settings,options),"with_weather":artifact["with_weather"],
                        "feature_names":artifact["feature_names"]},metrics=report,artifact=artifact,is_active=False)
                session.add(model)
                session.flush()
            for old in session.scalars(select(ModelVersion).where(ModelVersion.source==settings.bike_source,
                    ModelVersion.kind=="random_forest",ModelVersion.is_active.is_(True))):
                old.is_active = False
            model.is_active = True
            job.model_version_id = model.id
        # If a new training attempt has insufficient data or prefers baseline, retain the old model.
        job.finished_at = utcnow()
        session.commit()
        return job
    except BaseException as exc:
        session.rollback()
        failed = session.get(TrainingJob,job_id)
        failed.status,failed.finished_at,failed.error_summary = "failed",utcnow(),type(exc).__name__
        session.commit()
        raise
