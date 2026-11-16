"""Calendar boundaries and source-scoped reads against isolated SQLite fixtures."""
from datetime import datetime, timedelta

import pytest

from backend.app.calendar_series import calendar_window
from tests.test_api import api, bike, NOW
from shared.time import UTC


@pytest.mark.parametrize('period,anchor,hours', [
    ('day', '2026-11-01', 25), ('day', '2026-03-08', 23),
    ('week', '2026-W44', 169), ('month', '2026-11', 721),
])
def test_calendar_boundaries_follow_new_york_dst(period, anchor, hours):
    start, end = calendar_window(period, anchor)
    assert (end - start).total_seconds() == hours * 3600


def test_history_selection_keeps_zero_null_and_gap_and_filters_source(api):
    client, session, _ = api
    start = datetime(2026, 11, 8, 5, tzinfo=UTC)
    bike(session, start + timedelta(hours=1), 0)
    bike(session, start + timedelta(hours=2), 8, quality='inactive', renting=False)
    bike(session, start + timedelta(hours=1), 99, source='seoul')
    response = client.get('/api/eda/series?period=day&anchor=2026-11-08')
    assert response.status_code == 200
    data = response.json()
    assert data['timezone'] == 'America/New_York' and not data['partial_period']
    assert len(data['items']) == 1
    assert [p['value'] for p in data['items'][0]['points']] == [0, None]
    assert data['items'][0]['points'][1]['gap_before'] is True
    assert '99' not in str([p['value'] for p in data['items'][0]['points']])


def test_current_period_is_clipped_to_now_and_unpublished_rows_are_excluded(api):
    client, session, _ = api
    bike(session, NOW - timedelta(hours=1), 8)
    bike(session, NOW - timedelta(minutes=1), 9, status='running')
    response = client.get('/api/eda/series?period=month&anchor=2026-11')
    assert response.status_code == 200
    data = response.json()
    assert data['partial_period'] is True
    assert datetime.fromisoformat(data['available_until_utc'].replace('Z', '+00:00')) == NOW
    assert len(data['items'][0]['points']) == 1


def test_calendar_includes_real_archive_without_replacing_live_or_using_estimates(api):
    client,session,_=api
    start=datetime(2026,11,8,5,tzinfo=UTC)
    bike(session,start+timedelta(hours=1),4)
    bike(session,start+timedelta(hours=1,seconds=10),99,source='citibike_historical')
    bike(session,start+timedelta(hours=2),8,source='citibike_historical')
    bike(session,start+timedelta(hours=3),77,source='citibike_estimated')
    data=client.get('/api/eda/series?period=day&anchor=2026-11-08').json()
    assert [p['value'] for p in data['items'][0]['points']]==[4,8]


@pytest.mark.parametrize('query', [
    'period=day&anchor=2026-02-30', 'period=week&anchor=2026-W99',
    'period=month&anchor=2026-13', 'period=day&anchor=2027-01-01',
    'period=year&anchor=2026-11',
])
def test_invalid_or_future_selections_are_rejected(api, query):
    client, _, _ = api
    assert client.get('/api/eda/series?' + query).status_code == 422


def test_missing_station_returns_404_in_requested_source(api):
    client, session, _ = api
    bike(session, NOW - timedelta(hours=1), 2, source='seoul')
    assert client.get('/api/eda/series?period=day&anchor=2026-11-08&station_id=00001').status_code == 404
