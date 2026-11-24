"""Compute on workers, atomically publish bounded JSON snapshots to MySQL."""
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import json
import math

import numpy as np
import pandas as pd
from sqlalchemy import delete, select

from analysis.config import AnalysisOptions
from analysis.statistics import period_start
from eda.dataset import load_frame, mark_latest_slots
from eda.decomposition import decompose
from eda.patterns import calendar_aggregates
from eda.statistics import correlation_tables, daily_coverage
from shared.cadence import SamplingCadence
from shared.eda_snapshots import VERSION, SNAPSHOT_SERVICE, PUBLISHER_SERVICE, WINDOWS, snapshot_key, empty_chart
from shared.models import ServiceRun, Station
from shared.time import as_utc, utcnow

# The 90-day window at a five-minute cadence is 259,200 rows for 10 stations.
# This runs on the analysis worker; Render never materializes this frame.
MAX_ROWS = 500000


def json_value(value):
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    return None if isinstance(value, float) and not math.isfinite(value) else value


def records(frame):
    return json_value(frame.to_dict(orient='records'))


def matrix(data):
    return [{'': str(name), **json_value(row.to_dict())} for name, row in data.iterrows()]


def input_fingerprint(frame, stations, options, cutoff, windows):
    # Hash actual contents: corrections/deletions, quality flags, weather units
    # and links matter even when MAX(id) and latest observation do not change.
    metadata = dict(version=VERSION, options=options.as_dict(), windows=windows,
        hour=cutoff.replace(minute=0, second=0, microsecond=0).isoformat(),
        stations=[dict(id=s.station_id, name=s.name, capacity=s.capacity,
            latitude=str(s.latitude), longitude=str(s.longitude)) for s in stations])
    digest = sha256(json.dumps(metadata, sort_keys=True).encode())
    digest.update(pd.util.hash_pandas_object(frame, index=False).values.tobytes())
    return digest.hexdigest()


def calculate_snapshots(frame, stations, firsts, settings, options, cutoff, windows):
    cadence = SamplingCadence(options.expected_interval_seconds, options.sampling_schedule)
    source = settings.bike_source
    for days in windows:
        start = cutoff - timedelta(days=days)
        selected = frame.loc[frame.sampled_at >= start]
        base = empty_chart(source, 'trend')
        base.update(status='available', range_start_utc=start.isoformat(), cutoff_utc=cutoff.isoformat(),
            timezone=options.timezone_name, raw_rows=len(selected),
            stations=[dict(station_id=s.station_id, name=s.name) for s in stations])
        coverage = daily_coverage(selected, stations, firsts, cadence, options, start, cutoff)
        tables = {name: records(value) for name, value in calendar_aggregates(selected, coverage, cutoff).items()}
        for kind in ('trend', 'seasonality'):
            yield kind, days, None, {**base, **tables, 'chart': kind}
        correlations = correlation_tables(selected)
        global_matrix = correlations['ALL']['correlation']
        yield 'correlation', days, None, {**base, 'chart': 'correlation', 'correlation': matrix(global_matrix)}
        metadata, components = decompose(selected, stations, cadence, start, cutoff, options.timezone_name)
        for station in stations:
            station_frame = selected.loc[selected.station_id == station.station_id]
            station_base = {**base, 'stations': [dict(station_id=station.station_id, name=station.name)],
                'raw_rows': len(station_frame)}
            yield 'correlation', days, station.station_id, {**station_base, 'chart': 'correlation',
                'correlation': matrix(correlations.get(station.station_id,
                    {'correlation': global_matrix * np.nan})['correlation'])}
            yield 'decomposition', days, station.station_id, {**station_base, 'chart': 'decomposition',
                'decomposition_status': [item for item in metadata if item['station_id'] == station.station_id],
                'decomposition': records(components.loc[components.station_id == station.station_id])}


def publish_once(session, settings, options=None, *, cutoff=None, rebuild=False, windows=WINDOWS):
    """Caller holds the EDA service lock. No external calls or model training."""
    options = options or AnalysisOptions.load()
    windows = tuple(sorted(set(windows)))
    if not windows or any(day not in WINDOWS for day in windows):
        raise ValueError('Unsupported EDA snapshot window')
    cutoff = period_start(as_utc(cutoff) if cutoff else utcnow(), 300)
    if cutoff > utcnow():
        raise ValueError('EDA cutoff cannot be in the future')
    source = settings.bike_source
    stations = list(session.scalars(select(Station).where(Station.source == source,
        Station.is_monitored.is_(True)).order_by(Station.station_id).limit(101)))
    if len(stations) > 100:
        raise ValueError('EDA supports at most 100 monitored stations per source')
    settings = replace(settings, station_ids=tuple(s.station_id for s in stations))
    config = dict(source=source, windows=list(windows), station_ids=list(settings.station_ids))
    config_hash = sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    existing = session.scalar(select(ServiceRun).where(ServiceRun.service_name == PUBLISHER_SERVICE,
        ServiceRun.source == source, ServiceRun.calculation_version == VERSION,
        ServiceRun.configuration_hash == config_hash, ServiceRun.scheduled_at == cutoff))
    previous = session.scalar(select(ServiceRun).where(ServiceRun.service_name == PUBLISHER_SERVICE,
        ServiceRun.source == source, ServiceRun.calculation_version == VERSION,
        ServiceRun.configuration_hash == config_hash, ServiceRun.status.in_(('success', 'skipped')))
        .order_by(ServiceRun.finished_at.desc(), ServiceRun.id.desc()).limit(1))
    previous_summary = dict(previous.summary or {}) if previous else {}
    if previous is not None and previous.scheduled_at > cutoff:
        # A historical analysis/demo must not replace current web charts.
        return previous
    now = utcnow()
    run = existing or ServiceRun(service_name=PUBLISHER_SERVICE, source=source,
        scheduled_at=cutoff, started_at=now, heartbeat_at=now, status='running', attempt_count=0,
        calculation_version=VERSION, configuration_hash=config_hash, configuration=config, result_count=0)
    session.add(run)
    run.status, run.started_at, run.finished_at, run.error_summary = 'running', now, None, None
    run.attempt_count += 1
    session.commit()
    try:
        frame, stations, firsts = load_frame(session, settings, options,
            cutoff - timedelta(days=max(windows)), cutoff, MAX_ROWS, include_weather=True)
        frame = mark_latest_slots(frame, SamplingCadence(options.expected_interval_seconds, options.sampling_schedule))
        fingerprint = input_fingerprint(frame, stations, options, cutoff, windows)
        stored = list(session.scalars(select(ServiceRun).where(ServiceRun.source == source,
            ServiceRun.service_name == SNAPSHOT_SERVICE, ServiceRun.calculation_version == VERSION)))
        expected = {snapshot_key(source, kind, days, sid) for days in windows
            for kind, sid in [('trend', None), ('seasonality', None), ('correlation', None)]
            + [(kind, station.station_id) for station in stations for kind in ('correlation', 'decomposition')]}
        present = {row.configuration_hash for row in stored if row.status == 'success'}
        if not rebuild and previous_summary.get('fingerprint') == fingerprint and expected <= present:
            run.status, run.result_count = 'skipped', 0
            run.summary = {**previous_summary, 'reason': 'unchanged_inputs'}
        else:
            finished = utcnow()
            new_ids = []
            for kind, days, sid, data in calculate_snapshots(frame, stations, firsts, settings, options, cutoff, windows):
                data.update(published_at=finished.isoformat())
                snapshot = ServiceRun(service_name=SNAPSHOT_SERVICE, source=source,
                    scheduled_at=cutoff, started_at=now, finished_at=finished, heartbeat_at=finished,
                    status='success', attempt_count=1, calculation_version=VERSION,
                    configuration_hash=snapshot_key(source, kind, days, sid),
                    configuration=dict(kind=kind, days=days, station_id=sid),
                    summary=data, result_count=data['raw_rows'])
                # Rebuild in the same five-minute period replaces its own row.
                old = next((s for s in stored if s.scheduled_at == cutoff
                    and s.configuration_hash == snapshot.configuration_hash), None)
                if old is not None:
                    old.summary, old.finished_at, old.result_count = data, finished, data['raw_rows']
                    new_ids.append(old.id)
                else:
                    session.add(snapshot)
                    session.flush()
                    new_ids.append(snapshot.id)
            # Bound JSON storage. Only this publisher's previous snapshots for
            # these windows are replaced, in the same atomic transaction.
            obsolete = [s.id for s in stored if s.id not in new_ids and s.configuration.get('days') in windows]
            if obsolete:
                session.execute(delete(ServiceRun).where(ServiceRun.id.in_(obsolete),
                    ServiceRun.source == source, ServiceRun.service_name == SNAPSHOT_SERVICE,
                    ServiceRun.calculation_version == VERSION))
            run.status, run.result_count = 'success', len(new_ids)
            run.summary = dict(fingerprint=fingerprint, snapshot_count=len(new_ids),
                raw_rows=len(frame), station_count=len(stations), windows=list(windows), trained=False)
        run.finished_at = run.heartbeat_at = utcnow()
        session.commit()
        return run
    except BaseException as exc:
        session.rollback()
        run.status, run.error_summary = 'failed', type(exc).__name__
        run.finished_at = run.heartbeat_at = utcnow()
        run.result_count = 0
        session.commit()
        raise
