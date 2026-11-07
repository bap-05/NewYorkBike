"""Publish Gold atomically from completed Silver, independently of ingestion."""
import hashlib
import json
import math

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from analysis.dataset import calculate_results, selected_stations
from analysis.statistics import analysis_start, period_start
from shared.models import AnalysisResult, ServiceRun
from shared.time import as_utc, utcnow

VERSION = "analysis-v1"
IDENTITY = ("source", "station_id", "window_start", "window_end", "aggregation", "metric_name", "calculation_version", "configuration_hash")
COMPARABLE = ("metric_value", "sample_count", "observed_sample_count", "expected_sample_count", "coverage", "quality_status", "dimensions", "input_watermark")


def identity(row):
    return tuple(row[name] if isinstance(row, dict) else getattr(row, name) for name in IDENTITY)


def unchanged(old, row):
    for name in COMPARABLE:
        left, right = getattr(old, name), row[name]
        if isinstance(left, float) and isinstance(right, float):
            if not math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12):
                return False
        elif left != right:
            return False
    return True


def persist_results(session, rows):
    if not rows:
        return
    table = AnalysisResult.__table__
    dialect = session.get_bind().dialect.name
    mutable = [column.name for column in table.columns if column.name not in ("id", *IDENTITY)]
    if dialect == "mysql":
        statement = mysql_insert(table)
        statement = statement.on_duplicate_key_update(**{name: statement.inserted[name] for name in mutable})
    elif dialect == "sqlite":
        statement = sqlite_insert(table)
        statement = statement.on_conflict_do_update(index_elements=list(IDENTITY),
            set_={name: statement.excluded[name] for name in mutable})
    else:
        raise ValueError("Analysis persistence supports MySQL; SQLite is for isolated tests only")
    for offset in range(0, len(rows), 200):
        session.execute(statement, rows[offset:offset+200])


def analyze_once(session, settings, options, *, cutoff=None):
    instant = period_start(as_utc(cutoff) if cutoff is not None else utcnow(), 300)
    if instant > utcnow():
        raise ValueError("Analysis cutoff cannot be in the future")
    source = settings.bike_source
    stations = selected_stations(session, settings)
    requested = sorted(settings.station_ids or (s.station_id for s in stations))
    configuration = {**options.as_dict(), "station_ids": requested, "source": source,
                     "weather_max_age_seconds": settings.weather_max_age_seconds}
    digest = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    query = select(ServiceRun).where(ServiceRun.service_name == "analysis", ServiceRun.source == source,
        ServiceRun.scheduled_at == instant, ServiceRun.calculation_version == VERSION, ServiceRun.configuration_hash == digest)
    run = session.scalar(query)
    if run is not None and run.status in ("success", "skipped"):
        session.commit()
        return run
    started = utcnow()
    # The caller holds the analysis-specific lock; older running markers are abandoned.
    for abandoned in session.scalars(select(ServiceRun).where(ServiceRun.service_name == "analysis",
            ServiceRun.source == source, ServiceRun.status == "running")):
        if run is not None and abandoned.id == run.id:
            continue
        abandoned.status = "failed"
        abandoned.finished_at = abandoned.heartbeat_at = started
        abandoned.error_summary = "Interrupted before publication"
    if run is None:
        run = ServiceRun(service_name="analysis", source=source, scheduled_at=instant, started_at=started,
            heartbeat_at=started, status="running", attempt_count=1, calculation_version=VERSION,
            configuration_hash=digest, configuration=configuration, result_count=0)
        session.add(run)
    else:
        run.status = "running"
        run.started_at = run.heartbeat_at = started
        run.finished_at = None
        run.error_summary = None
        run.attempt_count += 1
    session.commit()  # Durable control marker. No Gold has changed yet.
    run_id = run.id
    try:
        start = analysis_start(instant, options)
        ids = [s.station_id for s in stations]
        generated, summary = calculate_results(session, settings, options, instant, stations)
        existing = {identity(row): row for row in session.scalars(select(AnalysisResult).where(
            AnalysisResult.source == source, AnalysisResult.station_id.in_(ids), AnalysisResult.window_start >= start,
            AnalysisResult.window_start < instant, AnalysisResult.calculation_version == VERSION,
            AnalysisResult.configuration_hash == digest))}
        for row in generated:
            row.update(calculation_version=VERSION, configuration_hash=digest,
                       service_run_id=run_id, calculated_at=started)
        changed = [row for row in generated if identity(row) not in existing or not unchanged(existing[identity(row)], row)]
        persist_results(session, changed)
        run.input_watermark = summary.pop("input_watermark")
        run.result_count = len(changed)
        run.summary = {**summary, "changed_metrics": len(changed),
            "skip_reason": None if changed else "no_changed_statistics_or_no_published_data"}
        run.finished_at = run.heartbeat_at = utcnow()
        run.status = "success" if changed else "skipped"
        session.commit()  # New/updated Gold and completion become visible together.
        session.expire_all()  # Core upserts must not leave stale ORM objects in a reused session.
        return run
    except BaseException as exc:
        session.rollback()
        failed = session.get(ServiceRun, run_id)
        failed.status = "failed"
        failed.finished_at = failed.heartbeat_at = utcnow()
        failed.result_count = 0
        failed.error_summary = type(exc).__name__  # No DB URL, parameters, or secrets.
        session.commit()
        raise
