"""Model payloads live in MySQL JSON; disposable runners need no model files."""
import hashlib
import json

from sqlalchemy import select

from shared.models import ModelVersion


def feature_policy(settings,options):
    return {"version":"prediction-features-v1","horizon_seconds":options.horizon_seconds,
        "timestamp_tolerance_seconds":options.timestamp_tolerance_seconds,
        "max_bike_age_seconds":options.max_bike_age_seconds,
        "weather_max_age_seconds":settings.weather_max_age_seconds}


def baseline_model(session,source,now):
    digest = hashlib.sha256(b"persistence-v1:sampled_at+1800").hexdigest()
    model = session.scalar(select(ModelVersion).where(ModelVersion.source==source,ModelVersion.identity_hash==digest))
    if model is None:
        model = ModelVersion(source=source,name="Persistence +30 minutes v1",kind="persistence",
            identity_hash=digest,created_at=now,feature_config={"horizon_seconds":1800},metrics={},
            artifact={"format":"persistence-v1","rule":"predicted_bikes = available_bikes at input_time"},is_active=False)
        session.add(model)
        session.flush()
    return model


def active_model(session,source,cutoff,settings,options):
    models = session.scalars(select(ModelVersion).where(ModelVersion.source==source,
        ModelVersion.kind=="random_forest",ModelVersion.is_active.is_(True),
        ModelVersion.created_at<=cutoff,ModelVersion.train_end<=cutoff).order_by(ModelVersion.created_at.desc(),ModelVersion.id.desc()))
    return next((m for m in models if m.feature_config.get("policy")==feature_policy(settings,options)),None)


def model_digest(report,artifact,settings,options):
    return hashlib.sha256(json.dumps({"dataset_hash":report["dataset_hash"],
        "selected":artifact["parameters"],"with_weather":artifact["with_weather"],
        "library":artifact["sklearn_version"],"policy":feature_policy(settings,options)},sort_keys=True).encode()).hexdigest()
