"""EDA snapshot routes use only a temporary directory; no production DB writes."""
from datetime import datetime
import json

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine

from backend.app.config import ApiOptions
from backend.app.main import create_app
from shared.time import UTC

NOW = datetime(2026, 11, 9, 15, tzinfo=UTC)


@pytest.fixture
def eda_api(tmp_path, settings):
    engine = create_engine('sqlite://')
    app = create_app(settings=settings, options=ApiOptions(eda_report_dir=str(tmp_path)),
        engine=engine, clock=lambda: NOW)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, tmp_path
    engine.dispose()


def snapshot(root, name='test-report', source='citibike', generated='2026-11-09T14:00:00+00:00'):
    directory = root / name
    (directory / 'figures').mkdir(parents=True)
    (directory / 'figures' / 'histograms.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'test-only')
    (directory / 'report.html').write_text('test-only completion marker')
    payload = {'version': 'eda-v1', 'source': source, 'database_written': False, 'model_trained': False,
        'generated_at_utc': generated, 'window_start_utc': '2026-11-02T05:00:00+00:00',
        'cutoff_utc': '2026-11-09T12:00:00+00:00', 'station_count': 1, 'raw_rows': 10,
        'deduplicated_rows': 9, 'usable_bike_rows': 8, 'usable_bikes_without_usable_weather': 1,
        'outlier_flag_count': 1, 'outlier_observation_count': 1,
        'figures': [{'file': 'figures/histograms.png', 'title': 'Test only histogram'}],
        'descriptive_statistics': [{'station_id': '001', 'column': 'available_bikes', 'count': 8,
            'mean': 0, 'median': 0, 'std_population': 0, 'mode_values': [0], 'mode_count': 1,
            'modes_truncated': False}], 'private_extra_field': 'must-not-be-published'}
    path = directory / 'summary.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    return directory, payload


def test_missing_report_returns_clear_state_without_database_access(eda_api):
    client, _ = eda_api
    assert client.get('/api/eda').json() == {'status': 'missing', 'item': None}


def test_latest_completed_source_scoped_snapshot_and_only_public_fields(eda_api):
    client, root = eda_api
    snapshot(root, name='old', generated='2026-11-09T13:00:00+00:00')
    snapshot(root, name='new')
    snapshot(root, name='seoul-newer', source='seoul', generated='2026-11-09T14:30:00+00:00')
    result = client.get('/api/eda')
    assert result.status_code == 200
    item = result.json()['item']
    assert item['report_id'] == 'new'
    assert item['statistics'][0]['station_id'] == '001'
    assert item['statistics'][0]['mean'] == 0
    assert 'must-not-be-published' not in result.text
    assert str(root) not in result.text
    assert client.get('/api/eda?source=seoul').json()['item']['report_id'] == 'seoul-newer'


def test_only_whitelisted_png_manifest_files_are_served(eda_api):
    client, root = eda_api
    directory, _ = snapshot(root)
    image = client.get('/api/eda/reports/test-report/figures/histograms.png')
    assert image.status_code == 200 and image.headers['content-type'] == 'image/png'
    assert image.headers['x-content-type-options'] == 'nosniff'
    assert client.get('/api/eda/reports/test-report/figures/histograms.png?source=seoul').status_code == 404
    (directory / 'figures' / 'report_preview.png').write_bytes(b'\x89PNG\r\n\x1a\n')
    assert client.get('/api/eda/reports/test-report/figures/report_preview.png').status_code == 404
    assert client.get('/api/eda/reports/test-report/figures/summary.json').status_code == 422



def test_extended_time_series_images_and_day_ahead_contract(eda_api):
    client, root = eda_api
    directory, payload = snapshot(root)
    (directory / 'figures' / 'scatter_week.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'test-only')
    payload['figures'].append({'file': 'figures/scatter_week.png', 'title': 'Phân tán theo tuần'})
    payload['day_ahead'] = {'items': [{'station_id': '001', 'station_name': 'Isolated test station',
        'status': 'available', 'reason': None, 'target_date': '2026-11-10',
        'target_start_utc': '2026-11-10T05:00:00+00:00', 'target_end_utc': '2026-11-11T05:00:00+00:00',
        'input_cutoff_utc': '2026-11-09T12:00:00+00:00', 'capacity': 50, 'qualified_days': 7,
        'predicted_mean_bikes': 0, 'availability_class': 'low', 'evaluation_samples': 0,
        'evaluation_status': 'insufficient_data', 'mae': None, 'rmse': None, 'classification_accuracy': None}]}
    (directory / 'summary.json').write_text(json.dumps(payload), encoding='utf-8')
    response = client.get('/api/eda')
    assert response.status_code == 200
    assert response.json()['item']['day_ahead'][0]['predicted_mean_bikes'] == 0
    assert client.get('/api/eda/reports/test-report/figures/scatter_week.png').status_code == 200


@pytest.mark.parametrize('change', ['unfinished', 'future', 'nonfinite', 'traversal', 'not_png', 'malformed'])
def test_invalid_or_unfinished_reports_are_not_published(eda_api, change):
    client, root = eda_api
    directory, data = snapshot(root)
    if change == 'unfinished':
        (directory / 'report.html').unlink()
    elif change == 'future':
        data['generated_at_utc'] = '2026-11-10T15:00:00+00:00'
    elif change == 'nonfinite':
        data['descriptive_statistics'][0]['mean'] = float('nan')
    elif change == 'traversal':
        data['figures'][0]['file'] = 'figures/../../outside.png'
    elif change == 'not_png':
        (directory / 'figures' / 'histograms.png').write_text('<html>not an image</html>')
    elif change == 'malformed':
        data = []
    (directory / 'summary.json').write_text(json.dumps(data), encoding='utf-8')
    response = client.get('/api/eda')
    assert response.status_code == 200
    if change == 'traversal':
        assert response.json()['item']['figures'] == []
        assert client.get('/api/eda/reports/test-report/figures/histograms.png').status_code == 404
    else:
        assert response.json()['status'] == 'missing'
