"""Daily immutable forecast publications and matured-hour scoring in MySQL.

Uses the existing service-run ledger: original report and actual evaluations are
separate JSON fields. Call under the prediction advisory lock, never from GET.
"""
from copy import deepcopy
from datetime import datetime, time, timedelta
import hashlib
import json
from math import sqrt
from zoneinfo import ZoneInfo

from sqlalchemy import select

from analysis.config import AnalysisOptions
from analysis.statistics import usable_bike
from eda.day_ahead import build_report
from eda.patterns import availability_class
from shared.cadence import SamplingCadence
from shared.models import BikeObservation, ServiceRun
from shared.repositories.silver import bike_observations
from shared.time import UTC, as_utc, utcnow

ZONE = ZoneInfo('America/New_York')
VERSION = 'day-ahead-v1'
SERVICE = 'day_ahead'


def daily_period(instant):
    return datetime.combine(instant.astimezone(ZONE).date(), time.min, ZONE).astimezone(UTC)


def publish_once(session, settings):
    """At most one successful publication per NY issue day; never backdate."""
    cutoff = as_utc(utcnow())
    period = daily_period(cutoff)
    ids = list(session.scalars(select(ServiceRun.id).where(ServiceRun.service_name == SERVICE,
        ServiceRun.source == settings.bike_source, ServiceRun.scheduled_at == period,
        ServiceRun.status == 'success', ServiceRun.finished_at.is_not(None))))
    if ids:
        return session.get(ServiceRun, max(ids))
    options = AnalysisOptions.load()
    configuration = {'source': settings.bike_source, 'station_ids': sorted(settings.station_ids),
        'expected_interval_seconds': options.expected_interval_seconds,
        'sampling_schedule': options.as_dict()['sampling_schedule'], 'minimum_coverage': .8,
        'evaluation_grace_seconds': options.ingestion_grace_seconds}
    digest = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    report = build_report(session, settings, cutoff, options)
    if not any(h['status'] == 'available' for station in report['day_ahead']
            for h in station['hourly_forecasts']):
        # Retry next tick if ingestion is down; don't freeze a whole day of empty results.
        session.rollback()
        return None
    issued = as_utc(utcnow())
    if daily_period(issued) != period or any(datetime.fromisoformat(h['target_start_utc']) <= issued
            for station in report['day_ahead'] for h in station['hourly_forecasts']):
        raise RuntimeError('Publication crossed its issue day; retry with a new cutoff')
    report.update(issued_at={'utc': issued.isoformat(), 'local': issued.astimezone(ZONE).isoformat()}, persisted=True)
    run = ServiceRun(service_name=SERVICE, source=settings.bike_source, scheduled_at=period,
        started_at=cutoff, finished_at=issued, heartbeat_at=issued, status='success', attempt_count=1,
        calculation_version=VERSION, configuration_hash=digest, configuration=configuration,
        result_count=sum(len(s['hourly_forecasts']) for s in report['day_ahead']),
        summary={'report': report,
            'actual_evaluations': score_report(report, {}, {}, configuration, issued),
            'evaluation_updated_at': None})
    session.add(run)
    session.commit()
    return run


def hour_key(station_id, target_start):
    return station_id + '|' + target_start


def score_report(report, previous, observations, policy, cutoff):
    """Score original floats only after the complete hour, using real slot samples."""
    results = deepcopy(previous)
    cadence = SamplingCadence(policy['expected_interval_seconds'], policy.get('sampling_schedule', ()))
    grace = timedelta(seconds=policy.get('evaluation_grace_seconds', 120))
    for station in report['day_ahead']:
        for hour in station['hourly_forecasts']:
            key = hour_key(station['station_id'], hour['target_start_utc'])
            if results.get(key, {}).get('status') == 'available':
                continue  # Preserve the scored snapshot and its observation provenance.
            start, end = (as_utc(datetime.fromisoformat(hour[field]))
                for field in ('target_start_utc', 'target_end_utc'))
            value = hour['predicted_mean_bikes']
            result = {'station_id': station['station_id'], 'target_start_utc': start.isoformat(),
                'target_end_utc': end.isoformat(), 'hour_label': hour['hour_label'],
                'predicted_bikes': value, 'actual_bikes': None, 'absolute_error': None,
                'squared_error': None, 'classification_correct': None, 'coverage': None,
                'evaluated_at': None, 'observation_ids': []}
            if hour['status'] != 'available' or value is None:
                result['status'] = 'not_forecast'
            elif cutoff < end + grace:
                result['status'] = 'pending'
            else:
                slots = {}
                for row in observations.get(station['station_id'], ()):
                    if start <= row.sampled_at < end and row.collected_at <= cutoff:
                        tick = cadence.slot_at(row.sampled_at)
                        old = slots.get(tick)
                        rank = lambda b: (b.source != 'citibike_historical', b.sampled_at, b.collected_at, b.id)
                        if old is None or rank(row) > rank(old):
                            slots[tick] = row
                expected = sum(1 for _ in cadence.slots(start, end))
                valid = [row for row in slots.values() if usable_bike(row)]
                coverage = len(valid) / expected if expected else 0.
                result.update(coverage=min(1., coverage), status='awaiting_data')
                if expected and coverage >= policy.get('minimum_coverage', .8):
                    actual = sum(float(row.available_bikes) for row in valid) / len(valid)
                    error = value - actual
                    result.update(status='available', actual_bikes=actual, absolute_error=abs(error),
                        squared_error=error * error, evaluated_at=cutoff.isoformat(),
                        classification_correct=availability_class(value, station['capacity'])
                            == availability_class(actual, station['capacity']),
                        observation_ids=sorted(row.id for row in valid))
            results[key] = result
    return results


def published_runs(session, source, cutoff, days=31):
    # Sort IDs/metadata, not large JSON summaries (MySQL sort-buffer limits).
    first_day = cutoff.astimezone(ZONE).date() - timedelta(days=days - 1)
    first_period = datetime.combine(first_day, time.min, ZONE).astimezone(UTC)
    ids = list(session.scalars(select(ServiceRun.id).where(ServiceRun.service_name == SERVICE,
        ServiceRun.source == source, ServiceRun.status == 'success',
        ServiceRun.finished_at.is_not(None), ServiceRun.finished_at <= cutoff,
        ServiceRun.scheduled_at >= first_period
        ).order_by(ServiceRun.scheduled_at.desc(), ServiceRun.id.desc()).limit(days + 2)))
    return [session.get(ServiceRun, run_id) for run_id in ids]


def evaluate_pending(session, settings):
    cutoff = as_utc(utcnow())
    changed, scored = 0, 0
    for run in published_runs(session, settings.bike_source, cutoff):
        report = run.summary['report']
        previous = run.summary.get('actual_evaluations', {})
        due = [h for s in report['day_ahead'] for h in s['hourly_forecasts']
            if h['status'] == 'available'
            and previous.get(hour_key(s['station_id'], h['target_start_utc']), {}).get('status') != 'available'
            and datetime.fromisoformat(h['target_end_utc'])
                + timedelta(seconds=run.configuration['evaluation_grace_seconds']) <= cutoff]
        groups = {}
        if due:
            start = min(datetime.fromisoformat(h['target_start_utc']) for h in due)
            end = max(datetime.fromisoformat(h['target_end_utc']) for h in due)
            query = bike_observations(source=settings.bike_source, available_at=cutoff,
                include_unusable=True, include_archived=True).where(
                BikeObservation.station_id.in_([s['station_id'] for s in report['day_ahead']]),
                BikeObservation.sampled_at >= start, BikeObservation.sampled_at < end)
            for row in session.scalars(query):
                groups.setdefault(row.station_id, []).append(row)
        results = score_report(report, previous, groups, run.configuration, cutoff)
        if results != previous:
            scored += sum(r['status'] == 'available' and previous.get(k, {}).get('status') != 'available'
                for k, r in results.items())
            run.summary = {**run.summary, 'actual_evaluations': results, 'evaluation_updated_at': cutoff.isoformat()}
            run.heartbeat_at = cutoff
            changed += 1
    session.commit()
    return {'updated_publications': changed, 'newly_scored_hours': scored}


def actual_summary(runs, station_id):
    items = []
    for run in runs:
        issued = run.summary['report'].get('issued_at', {}).get('utc')
        for value in run.summary.get('actual_evaluations', {}).values():
            if value['station_id'] == station_id:
                items.append({**{k: v for k, v in value.items() if k != 'observation_ids'},
                    'publication_id': run.id, 'issued_at': issued})
    items.sort(key=lambda r: r['target_start_utc'], reverse=True)
    available = [r for r in items if r['status'] == 'available']
    return {'scored_hours': len(available),
        'pending_hours': sum(r['status'] == 'pending' for r in items),
        'awaiting_data_hours': sum(r['status'] == 'awaiting_data' for r in items),
        'not_forecast_hours': sum(r['status'] == 'not_forecast' for r in items),
        'mae': sum(r['absolute_error'] for r in available) / len(available) if available else None,
        'rmse': sqrt(sum(r['squared_error'] for r in available) / len(available)) if available else None,
        'classification_accuracy': sum(r['classification_correct'] for r in available) / len(available) if available else None,
        'items': items}
