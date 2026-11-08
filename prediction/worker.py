"""Publish forecasts and evaluate matured targets, independently of source APIs."""
from collections import Counter
from dataclasses import replace
from datetime import timedelta
import hashlib
import json

from sqlalchemy import select

from prediction.data import feature_values, load_history, nearest, stations_for, usable
from prediction.learning import infer
from prediction.registry import active_model, baseline_model
from shared.models import Prediction, ServiceRun
from shared.time import as_utc, sampling_slot, utcnow

VERSION = "prediction-v1"


def forecast_rows(stations,groups,settings,options,cutoff,model=None):
    rows = []
    for station in stations:
        history = groups[station.station_id]
        # Never search backwards for a valid sample after a newer inactive sample.
        entry = max(history,key=lambda e:(e["bike"].sampled_at,e["bike"].collected_at,e["bike"].id),default=None)
        row = {"source":settings.bike_source,"station_id":station.station_id,"input_cutoff_at":cutoff,
            "input_time":None,"target_at":None,"input_observation_id":None,"model_version_id":None,
            "status":"unavailable","reason":"missing_observation","raw_predicted_bikes":None,
            "predicted_bikes":None,"features":{}}
        if entry is None:
            rows.append(row)
            continue
        b = entry["bike"]
        target = b.sampled_at+timedelta(seconds=options.horizon_seconds)
        row.update(input_time=b.sampled_at,target_at=target,input_observation_id=b.id)
        if not usable(entry,options):
            row["reason"] = "inactive" if b.is_renting is False or b.is_installed is False or b.quality_status=="inactive" else "invalid_observation"
        elif (cutoff-b.source_observed_at).total_seconds() > options.max_bike_age_seconds or (cutoff-b.sampled_at).total_seconds() > options.max_bike_age_seconds:
            row["reason"] = "stale_observation"
        elif target <= cutoff:
            row["reason"] = "target_already_passed"
        elif station.capacity is not None and b.available_bikes > station.capacity:
            row["reason"] = "count_exceeds_current_capacity"
        else:
            features = feature_values(entry,history,station,settings,options)
            raw,reason,kind,model_id = float(b.available_bikes),"no_eligible_active_ml_model","baseline",None
            if model is not None:
                if features is None:
                    reason = "missing_lag30"
                elif model.artifact.get("with_weather") and features["weather"] is None:
                    reason = "missing_or_invalid_weather"
                else:
                    try:
                        raw = infer(model.artifact,features,station.station_id)
                        kind,model_id,reason = "ml",model.id,None
                    except Exception:
                        reason = "model_inference_error_or_unseen_station"
            row.update(status=kind,reason=reason,raw_predicted_bikes=raw,
                predicted_bikes=max(0.0,min(raw,station.capacity)) if station.capacity is not None else max(0.0,raw),
                model_version_id=model_id,features={"values":features,
                    "source_observed_at":b.source_observed_at.isoformat(),
                    "collection_published_at":entry["available_at"].isoformat(),
                    "current_capacity":station.capacity,"horizon_from":"input_observation.sampled_at",
                    "baseline_bikes":b.available_bikes})
        rows.append(row)
    return rows


def evaluate_pending(session,source,groups,options,cutoff):
    query = select(Prediction).join(ServiceRun,(ServiceRun.id==Prediction.service_run_id)&(ServiceRun.source==Prediction.source)).where(
        Prediction.source==source,Prediction.station_id.in_(list(groups)),Prediction.status.in_(("baseline","ml")),
        Prediction.actual_observation_id.is_(None),Prediction.target_at<=cutoff,
        Prediction.target_at>=cutoff-timedelta(days=options.history_days),
        ServiceRun.service_name=="prediction",ServiceRun.status=="success",ServiceRun.finished_at.is_not(None))
    count = 0
    for forecast in session.scalars(query):
        policy = session.get(ServiceRun,forecast.service_run_id).configuration
        original_options = replace(options,
            timestamp_tolerance_seconds=policy["timestamp_tolerance_seconds"],
            max_bike_age_seconds=policy["max_bike_age_seconds"])
        if cutoff < forecast.target_at+timedelta(seconds=original_options.timestamp_tolerance_seconds):
            continue
        actual = nearest(groups[forecast.station_id],forecast.target_at,original_options.timestamp_tolerance_seconds)
        if actual is None or not usable(actual,original_options):
            continue
        b = actual["bike"]
        if b.sampled_at <= forecast.issued_at:
            continue
        forecast.actual_observation_id,forecast.actual_bikes,forecast.actual_time = b.id,b.available_bikes,b.sampled_at
        forecast.target_offset_seconds = (b.sampled_at-forecast.target_at).total_seconds()
        forecast.evaluated_at = cutoff
        error = forecast.raw_predicted_bikes-b.available_bikes
        forecast.absolute_error,forecast.squared_error = abs(error),error**2
        forecast.served_absolute_error = abs(forecast.predicted_bikes-b.available_bikes)
        count += 1
    return count


def predict_once(session,settings,options):
    cutoff = as_utc(utcnow())
    period = sampling_slot(cutoff)
    configuration = {**options.as_dict(),"source":settings.bike_source,
        "station_ids":sorted(settings.station_ids or (s.station_id for s in stations_for(session,settings))),
        "weather_max_age_seconds":settings.weather_max_age_seconds}
    digest = hashlib.sha256(json.dumps(configuration,sort_keys=True).encode()).hexdigest()
    run = session.scalar(select(ServiceRun).where(ServiceRun.service_name=="prediction",ServiceRun.source==settings.bike_source,
        ServiceRun.scheduled_at==period,ServiceRun.calculation_version==VERSION,ServiceRun.configuration_hash==digest))
    if run is not None and run.status in ("success","skipped"):
        session.commit()
        return run
    for old in session.scalars(select(ServiceRun).where(ServiceRun.service_name=="prediction",
            ServiceRun.source==settings.bike_source,ServiceRun.status=="running")):
        old.status,old.finished_at,old.heartbeat_at,old.error_summary = "failed",cutoff,cutoff,"Interrupted before publication"
    if run is None:
        run = ServiceRun(service_name="prediction",source=settings.bike_source,scheduled_at=period,
            started_at=cutoff,heartbeat_at=cutoff,status="running",attempt_count=1,calculation_version=VERSION,
            configuration_hash=digest,configuration=configuration,result_count=0)
        session.add(run)
    else:
        run.status,run.started_at,run.heartbeat_at,run.finished_at,run.error_summary = "running",cutoff,cutoff,None,None
        run.attempt_count += 1
    session.commit()
    run_id = run.id
    try:
        stations,groups = load_history(session,settings,cutoff,options)
        model = active_model(session,settings.bike_source,cutoff,settings,options)
        baseline = baseline_model(session,settings.bike_source,cutoff)
        rows = forecast_rows(stations,groups,settings,options,cutoff,model)
        issued = utcnow()
        for row in rows:
            if row["status"] != "unavailable" and row["target_at"] <= issued:
                row.update(status="unavailable",reason="target_passed_during_computation",raw_predicted_bikes=None,predicted_bikes=None,model_version_id=None)
            if row["status"] == "baseline":
                row["model_version_id"] = baseline.id
            session.add(Prediction(**row,service_run_id=run_id,scheduled_at=period,issued_at=issued))
        evaluated = evaluate_pending(session,settings.bike_source,groups,options,cutoff)
        counts = Counter(r["status"] for r in rows)
        run.status = "success" if rows or evaluated else "skipped"
        run.result_count = len(rows)
        run.summary = {"statuses":dict(counts),"reasons":dict(Counter(r["reason"] for r in rows if r["reason"])),
            "evaluated_predictions":evaluated,"input_cutoff_at":cutoff.isoformat(),
            "requested_station_ids_missing_metadata":sorted(set(settings.station_ids)-{s.station_id for s in stations}),
            "horizon_seconds":options.horizon_seconds,"active_ml_model_id":model.id if model else None}
        run.input_watermark = max((e["available_at"] for history in groups.values() for e in history),default=None)
        run.finished_at = run.heartbeat_at = utcnow()
        session.commit()
        return run
    except BaseException as exc:
        session.rollback()
        run = session.get(ServiceRun,run_id)
        run.status,run.error_summary,run.result_count = "failed",type(exc).__name__,0
        run.finished_at = run.heartbeat_at = utcnow()
        session.commit()
        raise
