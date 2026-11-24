"""Live EDA reads published SQL observations without artifacts or DB writes."""
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select

from analysis.config import AnalysisOptions
from shared.models import BikeObservation, ServiceRun
from test_api import api, bike, weather, NOW
from test_clustering import populate, CUTOFF


def configure(app, monkeypatch):
    app.state.settings = replace(app.state.settings, station_ids=())
    monkeypatch.setattr(AnalysisOptions, 'load', classmethod(lambda cls: AnalysisOptions()))

    def forbidden(*args, **kwargs):
        pytest.fail('Live charts must not read report files or calculate forecasts')

    monkeypatch.setattr('backend.app.routers.eda.latest_report', forbidden)
    monkeypatch.setattr('backend.app.routers.eda.read_report', forbidden)
    monkeypatch.setattr('eda.hourly_forecast.forecast_hours', forbidden)


def test_live_calendar_and_decomposition_need_no_reports_and_follow_db_deletion(api, monkeypatch):
    client, session, app = api
    configure(app, monkeypatch)
    app.state.clock = lambda: CUTOFF
    populate(session, days=21)
    before = session.scalar(select(func.count()).select_from(BikeObservation))
    for kind in ('trend', 'seasonality'):
        response = client.get('/api/eda/chart-data', params={'kind': kind})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['data_source'] == 'database' and data['raw_rows'] == before
        assert len([row for row in data['weekly'] if row['station_id'] == 'TEST-0' and row['complete']]) >= 2
        assert data['decomposition'] == []
        assert all(row['mean_bikes'] is None for row in data['weekly'] if not row['complete'])
    response = client.get('/api/eda/chart-data?kind=decomposition&station_id=TEST-0')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['decomposition_status'][0]['status'] == 'available'
    assert len(data['stations']) == 1
    for row in data['decomposition']:
        assert row['station_id'] == 'TEST-0'
        assert row['observed'] == pytest.approx(row['trend'] + row['seasonal'] + row['residual'])
    assert session.scalar(select(func.count()).select_from(BikeObservation)) == before
    assert session.scalar(select(func.count()).select_from(ServiceRun)) == 0
    session.execute(delete(BikeObservation))
    session.commit()
    fresh = client.get('/api/eda/chart-data?kind=decomposition&station_id=TEST-0').json()
    assert fresh['raw_rows'] == 0 and fresh['decomposition'] == []
    assert fresh['decomposition_status'][0]['status'] == 'insufficient_data'


def test_live_correlation_preserves_zero_null_and_source_isolation(api, monkeypatch):
    client, session, app = api
    configure(app, monkeypatch)
    for index in range(3):
        row = bike(session, NOW - timedelta(hours=3-index), index)
        sample = weather(session, row, temperature=index*2)
        sample.units = {**sample.units, 'wind_speed_10m': 'm/s'}
        session.commit()
    response = client.get('/api/eda/chart-data?kind=correlation')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['raw_rows'] == 3
    matrix = {row['']: row for row in data['correlation']}
    assert matrix['available_bikes']['temperature'] == pytest.approx(1.)
    assert matrix['available_bikes']['humidity'] is None  # constant weather, never zero-filled
    changed = session.scalar(select(BikeObservation).where(BikeObservation.available_bikes == 2))
    changed.available_bikes = 0
    session.commit()
    fresh = client.get('/api/eda/chart-data?kind=correlation').json()
    assert fresh['correlation'] != data['correlation']
    other = client.get('/api/eda/chart-data?kind=correlation&source=seoul').json()
    assert other['raw_rows'] == 0 and other['stations'] == []
    assert session.scalar(select(func.count()).select_from(ServiceRun)) == 0


def test_live_chart_validation_limits_and_empty_data(api, monkeypatch):
    from backend.app import live_eda
    client, session, app = api
    configure(app, monkeypatch)
    assert client.get('/api/eda/chart-data?kind=unknown').status_code == 422
    assert client.get('/api/eda/chart-data?kind=trend&days=91').status_code == 422
    assert client.get('/api/eda/chart-data?kind=trend&days=1').status_code == 422
    assert client.get('/api/eda/chart-data?kind=trend&station_id=missing').status_code == 404
    empty = client.get('/api/eda/chart-data?kind=trend').json()
    assert empty['raw_rows'] == 0 and empty['daily'] == []
    bike(session, NOW - timedelta(hours=2), 0)
    monkeypatch.setattr(live_eda, 'MAX_ROWS', 0)
    response = client.get('/api/eda/chart-data?kind=trend')
    assert response.status_code == 422
    assert 'Too many observations' in response.json()['detail']


def test_live_charts_include_monitored_history_outside_worker_station_config(api, monkeypatch):
    client, session, app = api
    configure(app, monkeypatch)
    app.state.clock = lambda: CUTOFF
    populate(session, station_count=3, days=21)
    app.state.settings = replace(app.state.settings, station_ids=('TEST-1',))
    response = client.get('/api/eda/chart-data?kind=trend')
    assert response.status_code == 200, response.text
    data = response.json()
    assert {row['station_id'] for row in data['stations']} == {'TEST-0', 'TEST-1', 'TEST-2'}
    assert {row['station_id'] for row in data['weekly'] if row['complete']} == {'TEST-0', 'TEST-1', 'TEST-2'}


def test_overlapping_chart_requests_are_bounded_and_release_after_failure(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from backend.app import live_eda
    from fastapi import HTTPException

    started, finish = Event(), Event()

    def blocked(*args):
        started.set()
        assert finish.wait(5)
        raise ValueError('test failure must release the calculation slot')

    monkeypatch.setattr(live_eda, '_read_chart_data', blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(live_eda.read_chart_data, None, 'citibike', 'trend', 28)
        try:
            assert started.wait(5)
            with pytest.raises(HTTPException) as error:
                live_eda.read_chart_data(None, 'citibike', 'correlation', 28)
            assert error.value.status_code == 429
            assert error.value.headers['Retry-After'] == '3'
        finally:
            finish.set()
        with pytest.raises(ValueError):
            first.result(timeout=5)
    monkeypatch.setattr(live_eda, '_read_chart_data', lambda *args: {'data_source': 'database'})
    assert live_eda.read_chart_data(None, 'citibike', 'trend', 28)['data_source'] == 'database'
