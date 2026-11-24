"""Worker publication and small, strictly read-only web chart queries."""
from dataclasses import replace
from datetime import timedelta
import re

import pytest
from sqlalchemy import delete, event, func, select

from analysis.config import AnalysisOptions
from eda import snapshots
from shared.eda_snapshots import SNAPSHOT_SERVICE
from shared.models import BikeObservation, ServiceRun
from test_api import api, bike, weather, NOW
from test_clustering import populate, CUTOFF


@pytest.fixture
def prepared(api, monkeypatch):
    client, session, app = api
    app.state.settings = replace(app.state.settings, station_ids=('TEST-1',))
    app.state.clock = lambda: CUTOFF
    monkeypatch.setattr(snapshots, 'utcnow', lambda: CUTOFF)
    populate(session, station_count=3, days=21)
    return client, session, app


def publish(session, app, **kwargs):
    return snapshots.publish_once(session, app.state.settings, AnalysisOptions(),
        cutoff=CUTOFF, windows=(28,), **kwargs)


def test_precomputed_charts_include_all_stations_without_http_calculation(prepared, monkeypatch):
    client, session, app = prepared
    original_rows = session.scalar(select(func.count()).select_from(BikeObservation))
    run = publish(session, app)
    assert run.status == 'success' and run.result_count == 9
    statements = []
    def record(conn, cursor, statement, params, context, many):
        statements.append(statement)
    event.listen(app.state.engine, 'before_cursor_execute', record)
    monkeypatch.setattr(snapshots, 'calculate_snapshots', lambda *a: pytest.fail('HTTP must not calculate EDA'))
    try:
        for kind in ('trend', 'seasonality', 'correlation', 'decomposition'):
            params = dict(kind=kind)
            if kind == 'decomposition': params['station_id'] = 'TEST-0'
            response = client.get('/api/eda/chart-data', params=params)
            assert response.status_code == 200, response.text
            data = response.json()
            assert data['storage'] == 'precomputed' and data['data_source'] == 'database'
            assert data['published_at'] and data['status'] == 'available'
            if kind == 'trend':
                assert {s['station_id'] for s in data['stations']} == {'TEST-0', 'TEST-1', 'TEST-2'}
                assert len([r for r in data['weekly'] if r['station_id'] == 'TEST-0' and r['complete']]) >= 2
                assert all(r['mean_bikes'] is None for r in data['weekly'] if not r['complete'])
            if kind == 'decomposition':
                assert data['decomposition_status'][0]['status'] == 'available'
                for row in data['decomposition']:
                    assert row['observed'] == pytest.approx(row['trend'] + row['seasonal'] + row['residual'])
    finally:
        event.remove(app.state.engine, 'before_cursor_execute', record)
    assert not any(re.search(r'(?:FROM|JOIN)\s+["`]?'+BikeObservation.__table__.name+r'\b', sql, re.I)
        for sql in statements)
    assert session.scalar(select(func.count()).select_from(BikeObservation)) == original_rows


def test_unchanged_inputs_skip_and_deleted_snapshot_is_rebuilt(prepared, monkeypatch):
    client, session, app = prepared
    first = publish(session, app)
    assert first.status == 'success'
    count = session.scalar(select(func.count()).select_from(ServiceRun))
    again = publish(session, app)
    assert again.status == 'skipped' and again.summary['reason'] == 'unchanged_inputs'
    assert session.scalar(select(func.count()).select_from(ServiceRun)) == count
    session.execute(delete(ServiceRun).where(ServiceRun.service_name == SNAPSHOT_SERVICE))
    session.commit()
    assert client.get('/api/eda/chart-data?kind=trend').json()['status'] == 'missing'
    assert publish(session, app).status == 'success'
    assert client.get('/api/eda/chart-data?kind=trend').json()['status'] == 'available'


def test_content_corrections_and_deletions_are_detected(prepared):
    client, session, app = prepared
    publish(session, app)
    before = client.get('/api/eda/chart-data?kind=trend').json()['daily']
    bike = session.scalar(select(BikeObservation).order_by(BikeObservation.id))
    bike.available_bikes += 10
    session.commit()
    assert publish(session, app).status == 'success'
    assert client.get('/api/eda/chart-data?kind=trend').json()['daily'] != before
    session.execute(delete(BikeObservation))
    session.commit()
    publish(session, app)
    data = client.get('/api/eda/chart-data?kind=decomposition&station_id=TEST-0').json()
    assert data['raw_rows'] == 0 and data['decomposition'] == []
    assert data['decomposition_status'][0]['status'] == 'insufficient_data'


def test_failed_refresh_keeps_previous_snapshot_and_unrelated_service(prepared, monkeypatch):
    client, session, app = prepared
    publish(session, app)
    before = client.get('/api/eda/chart-data?kind=trend').json()
    original = snapshots.calculate_snapshots
    def broken(*args):
        yield next(original(*args))
        raise RuntimeError('deliberate isolated failure')
    monkeypatch.setattr(snapshots, 'calculate_snapshots', broken)
    with pytest.raises(RuntimeError): publish(session, app, rebuild=True)
    assert client.get('/api/eda/chart-data?kind=trend').json() == before
    assert session.scalar(select(func.count()).select_from(ServiceRun).where(ServiceRun.service_name == SNAPSHOT_SERVICE)) == 9


def test_api_missing_validation_source_and_station_isolation(prepared):
    client, session, app = prepared
    assert client.get('/api/eda/chart-data?kind=trend').json()['status'] == 'missing'
    for path in ('kind=unknown', 'kind=trend&days=91', 'kind=trend&days=7', 'kind=decomposition'):
        assert client.get('/api/eda/chart-data?' + path).status_code == 422
    assert client.get('/api/eda/chart-data?kind=trend&station_id=missing').status_code == 404
    publish(session, app)
    assert client.get('/api/eda/chart-data?kind=trend&source=seoul').json()['status'] == 'missing'
    selected = client.get('/api/eda/chart-data?kind=trend&station_id=TEST-1').json()
    assert {r['station_id'] for r in selected['daily']} == {'TEST-1'}
    assert len(client.get('/api/eda/chart-data?kind=correlation&station_id=TEST-1').json()['stations']) == 1


def test_replacement_is_bounded_and_preserves_other_services_and_newer_data(prepared, monkeypatch):
    client, session, app = prepared
    publish(session, app)
    unrelated = ServiceRun(service_name='day_ahead', source='citibike', scheduled_at=CUTOFF,
        started_at=CUTOFF, finished_at=CUTOFF, heartbeat_at=CUTOFF, status='success',
        attempt_count=1, calculation_version='other', configuration_hash='a'*64,
        configuration={}, summary={'keep': True}, result_count=1)
    session.add(unrelated)
    session.commit()
    other_id = unrelated.id
    later = CUTOFF + timedelta(minutes=5)
    monkeypatch.setattr(snapshots, 'utcnow', lambda: later)
    app.state.clock = lambda: later
    snapshots.publish_once(session, app.state.settings, AnalysisOptions(), cutoff=later,
        windows=(28,), rebuild=True)
    assert session.scalar(select(func.count()).select_from(ServiceRun).where(ServiceRun.service_name == SNAPSHOT_SERVICE)) == 9
    assert session.get(ServiceRun, other_id).summary == {'keep': True}
    before = client.get('/api/eda/chart-data?kind=trend').json()
    publish(session, app, rebuild=True)
    assert client.get('/api/eda/chart-data?kind=trend').json() == before


def test_correlation_weather_zero_null_and_updates(api, monkeypatch):
    client, session, app = api
    monkeypatch.setattr(snapshots, 'utcnow', lambda: NOW)
    for index in range(3):
        row = bike(session, NOW - timedelta(hours=3-index), index)
        sample = weather(session, row, temperature=index*2)
        sample.units = {**sample.units, 'wind_speed_10m': 'm/s'}
        session.commit()
    snapshots.publish_once(session, app.state.settings, AnalysisOptions(), cutoff=NOW, windows=(28,))
    data = client.get('/api/eda/chart-data?kind=correlation').json()
    matrix = {r['']: r for r in data['correlation']}
    assert matrix['available_bikes']['temperature'] == pytest.approx(1.)
    assert matrix['available_bikes']['humidity'] is None
