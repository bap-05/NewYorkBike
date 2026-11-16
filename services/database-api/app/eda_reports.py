"""Read completed EDA snapshots. Do not run EDA or expose HTML/CSV/model payloads."""
from datetime import datetime
import json
from pathlib import Path
import re

from backend.app.presenters import timestamp
from backend.app.schemas import EdaReport
from shared.config import ROOT
from shared.time import as_utc

REPORT_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$')
IMAGE_NAMES = frozenset(('timeseries.png', 'histograms.png', 'feature_histograms.png',
    'hour_profiles.png', 'weekday_profiles.png', 'coverage.png', 'missingness.png',
    'correlation_all.png', 'correlation_by_station.png', 'boxplots.png', 'scaling.png', 'no_data.png',
    'line_day.png', 'line_week.png', 'line_month.png', 'scatter_day.png', 'scatter_week.png',
    'scatter_month.png', 'histogram_day.png', 'histogram_week.png', 'histogram_month.png',
    'resampled_trend.png', 'weekly_seasonality.png'))
STAT_COLUMNS = frozenset(('available_bikes','available_docks','temperature','humidity','rain','wind_speed'))
STAT_FIELDS = ('station_id','column','count','mean','median','std_population','mode_values','mode_count','modes_truncated')
COUNT_FIELDS = ('station_count','raw_rows','deduplicated_rows','usable_bike_rows',
    'usable_bikes_without_usable_weather','outlier_flag_count','outlier_observation_count')


def report_root(options):
    path = Path(options.eda_report_dir)
    return (path if path.is_absolute() else ROOT / path).resolve()


def child_path(root, report_id):
    if not REPORT_ID.fullmatch(report_id):
        raise ValueError('Invalid report ID')
    path = (root / report_id).resolve()
    if path.parent != root:
        raise ValueError('Report must stay inside the report root')
    return path


def image_path(directory, filename):
    if filename not in IMAGE_NAMES:
        raise ValueError('Unsupported EDA image')
    path = (directory / 'figures' / filename).resolve()
    if not path.is_relative_to(directory) or not path.is_file() or path.stat().st_size > 16_000_000:
        raise ValueError('Invalid EDA image')
    with path.open('rb') as stream:
        if stream.read(8) != b'\x89PNG\r\n\x1a\n':
            raise ValueError('EDA image must be PNG')
    return path


def read_report(root, report_id, source, now):
    directory = child_path(root, report_id)
    manifest = (directory / 'summary.json').resolve()
    if not manifest.is_relative_to(directory) or not (directory / 'report.html').is_file():
        raise ValueError('Report is not complete')
    if manifest.stat().st_size > 4_000_000:
        raise ValueError('Report manifest too large')
    def invalid_constant(_):
        raise ValueError('Nonfinite manifest value')
    data = json.loads(manifest.read_text(encoding='utf-8'), parse_constant=invalid_constant)
    if not isinstance(data, dict):
        raise ValueError('EDA manifest must be an object')
    if data.get('version') != 'eda-v1' or data.get('source') != source:
        raise ValueError('Wrong EDA source or version')
    if data.get('database_written') is not False or data.get('model_trained') is not False:
        raise ValueError('Unsupported report provenance')
    generated = as_utc(datetime.fromisoformat(data['generated_at_utc']))
    begin = as_utc(datetime.fromisoformat(data['window_start_utc']))
    cutoff = as_utc(datetime.fromisoformat(data['cutoff_utc']))
    if not begin < cutoff <= generated <= as_utc(now):
        raise ValueError('Invalid EDA time range')
    figures = []
    for row in data['figures']:
        name = Path(row['file']).name
        if row['file'] != f'figures/{name}':
            continue
        image_path(directory, name)
        figures.append({'filename': name, 'title': row['title'],
            'url': f'/api/eda/reports/{report_id}/figures/{name}?source={source}'})
    statistics = [{key: row[key] for key in STAT_FIELDS} for row in data['descriptive_statistics']
                  if row['column'] in STAT_COLUMNS]
    if len(statistics) > 10000 or len(figures) > len(IMAGE_NAMES):
        raise ValueError('Too many EDA results')
    forecast = data.get('day_ahead') or {}
    if not isinstance(forecast, dict) or not isinstance(forecast.get('items', []), list):
        raise ValueError('Invalid day-ahead report')
    forecast_items = forecast.get('items', [])
    if len(forecast_items) > 10000:
        raise ValueError('Too many day-ahead results')
    return EdaReport(report_id=report_id, source=source, generated_at=timestamp(generated),
        input_sources=data.get('input_sources',{}),
        window_start=timestamp(begin), cutoff=timestamp(cutoff), figures=figures,
        statistics=statistics, day_ahead=forecast_items,
        **{key: data[key] for key in COUNT_FIELDS})


def latest_report(root, source, now):
    if not root.is_dir():
        return None
    latest = None
    for directory in root.iterdir():
        if not directory.is_dir():
            continue
        try:
            item = read_report(root, directory.name, source, now)
            if latest is None or item.generated_at.utc > latest.generated_at.utc:
                latest = item
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return latest
