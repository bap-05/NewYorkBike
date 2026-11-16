"""Stored publications are immutable; HTTP reads never create forecasts."""
from copy import deepcopy
from datetime import datetime, timedelta
import json

import pytest
from sqlalchemy import func, select

from analysis.config import AnalysisOptions
from prediction import day_ahead as worker
from shared.models import ServiceRun
from shared.time import UTC
from tests.test_api import api, bike, NOW


def report(cutoff, value=5):
    start = worker.daily_period(cutoff) + timedelta(days=1)
    hours = []
    for hour in range(24):
        at = start + timedelta(hours=hour)
        hours.append({'target_start_utc': at.isoformat(), 'target_end_utc': (at+timedelta(hours=1)).isoformat(),
            'local_hour': hour, 'hour_label': str(hour), 'status': 'available', 'reason': None,
            'history_days': 7, 'predicted_mean_bikes': value, 'availability_class': 'balanced',
            'evaluation_samples': 0, 'evaluation_status': 'insufficient_data', 'mae': None,
            'rmse': None, 'classification_accuracy': None})
    return {'source': 'citibike', 'generated_at': {'utc': cutoff.isoformat(), 'local': cutoff.isoformat()},
        'target_date': start.astimezone(worker.ZONE).date().isoformat(), 'day_ahead': [{
            'station_id': '00001', 'station_name': 'Isolated test station', 'capacity': 10,
            'status': 'available', 'reason': None, 'target_date': start.astimezone(worker.ZONE).date().isoformat(),
            'target_start_utc': start.isoformat(), 'target_end_utc': (start+timedelta(days=1)).isoformat(),
            'input_cutoff_utc': cutoff.isoformat(), 'qualified_days': 7, 'predicted_mean_bikes': value,
            'availability_class': 'balanced', 'evaluation_samples': 0, 'evaluation_status': 'insufficient_data',
            'mae': None, 'rmse': None, 'classification_accuracy': None, 'hourly_forecasts': hours}]}


@pytest.fixture
def publication(api, monkeypatch):
    client, session, app = api
    clock = [NOW]
    monkeypatch.setattr(worker, 'utcnow', lambda: clock[0])
    monkeypatch.setattr(worker.AnalysisOptions, 'load', lambda: AnalysisOptions(expected_interval_seconds=300))
    monkeypatch.setattr(worker, 'build_report', lambda session, settings, cutoff, options: report(cutoff))
    run = worker.publish_once(session, app.state.settings)
    return client, session, app, run, clock


def test_publish_once_freezes_original_forecast_and_is_idempotent(publication, monkeypatch):
    _, session, app, run, clock = publication
    original = deepcopy(run.summary['report'])
    clock[0] += timedelta(minutes=5)
    monkeypatch.setattr(worker, 'build_report', lambda *a: pytest.fail('Must not recompute a published forecast'))
    again = worker.publish_once(session, app.state.settings)
    assert again.id == run.id
    assert again.summary['report'] == original
    assert session.scalar(select(func.count()).select_from(ServiceRun)) == 1
    assert datetime.fromisoformat(original['issued_at']['utc']) < datetime.fromisoformat(original['day_ahead'][0]['target_start_utc'])


def test_api_reads_saved_forecast_and_never_publishes_or_scores(publication):
    client, session, app, run, _ = publication
    original = deepcopy(run.summary)
    response = client.get('/api/eda/day-ahead')
    assert response.status_code == 200, response.text
    item = response.json()['item']
    assert item['persisted'] and item['publication_id'] == run.id
    assert item['day_ahead'][0]['hourly_forecasts'][0]['predicted_mean_bikes'] == 5
    assert run.summary == original
    assert session.scalar(select(func.count()).select_from(ServiceRun)) == 1
    assert client.get('/api/eda/day-ahead?source=seoul').json()['item'] is None
    app.state.clock = lambda: NOW + timedelta(days=1)
    later = client.get('/api/eda/day-ahead').json()
    assert later['item'] is None and later['history'][0]['station_id'] == '00001'


def test_matured_hours_score_zero_actual_and_survive_retry(publication):
    client, session, app, run, clock = publication
    original = deepcopy(run.summary['report'])
    start = datetime.fromisoformat(original['day_ahead'][0]['hourly_forecasts'][0]['target_start_utc'])
    # Ten of twelve scheduled real observations: >80% coverage, actual zero.
    for index in range(10):
        bike(session, start + timedelta(minutes=index * 5), 0)
    clock[0] = start + timedelta(minutes=59)
    assert worker.evaluate_pending(session, app.state.settings)['newly_scored_hours'] == 0
    clock[0] = start + timedelta(hours=1, minutes=3)
    assert worker.evaluate_pending(session, app.state.settings)['newly_scored_hours'] == 1
    key = worker.hour_key('00001', start.isoformat())
    scored = run.summary['actual_evaluations'][key]
    assert scored['actual_bikes'] == 0 and scored['absolute_error'] == 5 and scored['squared_error'] == 25
    assert scored['classification_correct'] is False and len(scored['observation_ids']) == 10
    assert run.summary['report'] == original
    assert worker.evaluate_pending(session, app.state.settings)['newly_scored_hours'] == 0
    assert run.summary['actual_evaluations'][key] == scored
    summary = worker.actual_summary([run], '00001')
    assert summary['mae'] == summary['rmse'] == 5 and summary['scored_hours'] == 1
    # Even without today's next publication, the API keeps actual history visible.
    app.state.clock = lambda: clock[0]
    response = client.get('/api/eda/day-ahead')
    assert response.status_code == 200, response.text
    history = response.json()['history'][0]['issued_evaluation']
    assert history['scored_hours'] == 1
    assert 'observation_ids' not in response.text


def test_missing_or_invalid_samples_do_not_become_zero_or_get_replaced(publication):
    _, session, app, run, clock = publication
    start = datetime.fromisoformat(run.summary['report']['day_ahead'][0]['target_start_utc'])
    for index in range(10):
        bike(session, start + timedelta(minutes=index * 5), 0)
    # A newer invalid marker supersedes a valid observation in the same slot.
    bike(session, start + timedelta(seconds=30), 8, quality='inactive', renting=False)
    # Estimated observations may not repair the actual scoring cohort.
    bike(session, start + timedelta(minutes=55), 5, source='citibike_estimated')
    clock[0] = start + timedelta(hours=1, minutes=3)
    worker.evaluate_pending(session, app.state.settings)
    result = run.summary['actual_evaluations'][worker.hour_key('00001', start.isoformat())]
    assert result['status'] == 'awaiting_data' and result['actual_bikes'] is None
    assert result['absolute_error'] is None and result['coverage'] == .75
    # A genuine late observation can make the hour scorable on the next tick.
    bike(session, start + timedelta(minutes=50), 0)
    assert worker.evaluate_pending(session, app.state.settings)['newly_scored_hours'] == 1


def test_publication_crossing_midnight_is_not_backdated(api, monkeypatch):
    _, session, app = api
    cutoff = datetime(2026, 11, 10, 4, 59, 59, tzinfo=UTC)
    times = iter([cutoff, cutoff + timedelta(seconds=2)])
    monkeypatch.setattr(worker, 'utcnow', lambda: next(times))
    monkeypatch.setattr(worker, 'build_report', lambda s, settings, at, options: report(at))
    with pytest.raises(RuntimeError):
        worker.publish_once(session, app.state.settings)
    assert session.scalar(select(func.count()).select_from(ServiceRun)) == 0


def test_empty_forecasts_are_retried_instead_of_frozen(api, monkeypatch):
    _, session, app = api
    monkeypatch.setattr(worker, 'utcnow', lambda: NOW)
    empty = report(NOW)
    for hour in empty['day_ahead'][0]['hourly_forecasts']:
        hour.update(status='insufficient_data', predicted_mean_bikes=None)
    monkeypatch.setattr(worker, 'build_report', lambda *a: empty)
    assert worker.publish_once(session, app.state.settings) is None
    assert session.scalar(select(func.count()).select_from(ServiceRun)) == 0
    monkeypatch.setattr(worker, 'build_report', lambda s, settings, at, options: report(at))
    assert worker.publish_once(session, app.state.settings).status == 'success'


@pytest.mark.parametrize('instant,hours', [('2026-03-07T12:00:00+00:00',23), ('2026-10-31T12:00:00+00:00',25)])
def test_publication_day_boundaries_follow_dst(instant, hours):
    at = datetime.fromisoformat(instant)
    target = at.astimezone(worker.ZONE).date() + timedelta(days=1)
    from datetime import time
    begin = datetime.combine(target,time.min,worker.ZONE).astimezone(UTC)
    end = datetime.combine(target+timedelta(days=1),time.min,worker.ZONE).astimezone(UTC)
    assert (end-begin).total_seconds() == hours * 3600
