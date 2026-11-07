"""Publish a complete daily snapshot atomically, under the clustering-only lock."""
import hashlib
import json

from sqlalchemy import select

from clustering.algorithm import fit_clusters
from clustering.features import FEATURE_NAMES, bounds, calculate_features
from shared.models import ClusteringRun, ServiceRun, Station, StationCluster
from shared.time import as_utc, utcnow

VERSION = "clustering-v1"


def calculate(session, settings, options, instant):
    features, summary = calculate_features(session, settings, options, instant)
    members, parameters = fit_clusters(features, options)
    return members, parameters, summary


def cluster_once(session, settings, options, *, cutoff=None):
    instant = as_utc(cutoff) if cutoff is not None else utcnow()
    if instant > utcnow():
        raise ValueError("Clustering cutoff cannot be in the future")
    day, start, end = bounds(instant, options)
    source = settings.bike_source
    configuration = {**options.as_dict(), "source": source,
        "station_ids": sorted(settings.station_ids or session.scalars(
            select(Station.station_id).where(Station.source == source, Station.is_monitored.is_(True))))}
    digest = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    query = select(ClusteringRun).where(ClusteringRun.source == source, ClusteringRun.run_date == day,
        ClusteringRun.calculation_version == VERSION, ClusteringRun.configuration_hash == digest)
    run = session.scalar(query)
    if run is not None and run.status == "success":
        session.commit()
        return run
    started = utcnow()
    for abandoned in session.scalars(select(ClusteringRun).where(ClusteringRun.source == source,
            ClusteringRun.status == "running")):
        abandoned.status, abandoned.finished_at = "failed", started
        control = session.get(ServiceRun, abandoned.service_run_id)
        control.status, control.finished_at, control.heartbeat_at = "failed", started, started
        control.error_summary = "Interrupted before publication"
    control = session.get(ServiceRun, run.service_run_id) if run else None
    if control is None:
        control = ServiceRun(service_name="clustering", source=source, scheduled_at=end,
            started_at=started, heartbeat_at=started, status="running", attempt_count=1,
            calculation_version=VERSION, configuration_hash=digest, configuration=configuration, result_count=0)
        session.add(control)
        session.flush()
    else:
        control.status, control.started_at, control.heartbeat_at = "running", started, started
        control.finished_at, control.error_summary = None, None
        control.attempt_count += 1
    if run is None:
        run = ClusteringRun(source=source, run_date=day, service_run_id=control.id,
            window_start=start, window_end=end, input_cutoff=end, started_at=started,
            status="running", algorithm="StandardScaler+KMeans", calculation_version=VERSION,
            configuration_hash=digest, feature_config={**configuration, "feature_names": FEATURE_NAMES})
        session.add(run)
    else:
        run.status, run.started_at, run.finished_at = "running", started, None
    session.commit()
    run_id, control_id = run.id, control.id
    try:
        members, parameters, summary = calculate(session, settings, options, instant)
        watermark = summary["input_watermark"]
        summary["input_watermark"] = watermark.isoformat() if watermark else None
        for member in members:
            session.add(StationCluster(source=source, clustering_run_id=run_id,
                station_id=member["station_id"], cluster_label=member["cluster_label"],
                distance_to_centroid=member["distance_to_centroid"], feature_values=member["feature_values"],
                metadata_snapshot=member["metadata_snapshot"], sample_count=member["sample_count"],
                expected_sample_count=member["expected_sample_count"], coverage=member["coverage"],
                profile={"daily_coverage": member["daily_coverage"], "raw_statistics": member["raw_statistics"],
                    "hourly_mean_bikes": member["hourly_mean_bikes"], "excluded_samples": member["excluded_samples"]}))
        run.status, run.parameters, run.summary = parameters["status"], parameters, summary
        run.finished_at = control.finished_at = control.heartbeat_at = utcnow()
        control.status = "success" if run.status == "success" else "skipped"
        control.result_count, control.input_watermark = len(members), watermark
        control.summary = {"clustering_run_id": run_id, "clustering_status": run.status,
            "eligible_stations": summary["eligible_stations"], "reason": parameters.get("reason"),
            "selected_k": parameters.get("selected_k")}
        session.commit()
        return run
    except BaseException as exc:
        session.rollback()
        failed, failed_control = session.get(ClusteringRun, run_id), session.get(ServiceRun, control_id)
        failed.status, failed.finished_at = "failed", utcnow()
        failed_control.status, failed_control.result_count = "failed", 0
        failed_control.finished_at = failed_control.heartbeat_at = failed.finished_at
        failed_control.error_summary = type(exc).__name__
        session.commit()
        raise
