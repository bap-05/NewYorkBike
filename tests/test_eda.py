"""Isolated EDA fixtures; never seed the production database."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from analysis.config import AnalysisOptions
from eda.dataset import BASE_COLUMNS, NUMERIC, TIME_COLUMNS, load_frame, mark_latest_slots, statistical_values
from eda.report import json_safe, write_report
from eda.statistics import (correlation_tables, daily_coverage, descriptive_statistics,
    missingness, outlier_flags, scaling_comparison, temporal_profiles)
from shared.cadence import SamplingCadence
from shared.models import BikeObservation, CollectionRun, Station
from shared.time import UTC

START = datetime(2026, 11, 9, 11, tzinfo=UTC)
CHANGES = (('2026-11-09T11:25:00+00:00', 300),)


def make_frame(counts, minutes=None, *, weather=False, capacity=50):
    minutes = minutes if minutes is not None else list(range(0, len(counts) * 5, 5))
    rows = []
    for i, (count, minute) in enumerate(zip(counts, minutes)):
        at = START + timedelta(minutes=minute)
        rows.append({'observation_id': i, 'source': 'citibike', 'station_id': '001',
            'station_name': 'Isolated test station', 'capacity': capacity, 'quality_status': 'valid',
            'bike_usable': True, 'weather_usable': weather, 'weather_id': i if weather else None,
            'weather_units': None, 'weather_interval_seconds': 900 if weather else None,
            'available_bikes': count, 'available_docks': 10,
            'temperature': 10 if weather else None, 'humidity': 60 if weather else None,
            'rain': 0 if weather else None, 'wind_speed': 2 if weather else None,
            'sampled_at': at, 'collected_at': at, 'source_observed_at': at,
            'weather_time': at if weather else None})
    frame = pd.DataFrame(rows, columns=BASE_COLUMNS)
    for column in TIME_COLUMNS:
        frame[column] = pd.to_datetime(frame[column], utc=True)
    for column in NUMERIC + ['capacity']:
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    frame['sampled_at_local'] = frame.sampled_at.dt.tz_convert('America/New_York')
    frame['local_date'] = frame.sampled_at_local.dt.strftime('%Y-%m-%d')
    frame['local_hour'] = frame.sampled_at_local.dt.hour
    frame['local_weekday'] = frame.sampled_at_local.dt.day_of_week
    for column in ['bike_usable', 'weather_usable']:
        frame[column] = frame[column].astype(bool)
    return mark_latest_slots(frame, SamplingCadence(300))


def test_median_all_modes_and_population_std_preserve_zero_without_weather():
    frame = make_frame([0, 0, 1, 1])
    result = descriptive_statistics(frame)
    row = result.loc[(result.station_id == '001') & (result.column == 'available_bikes')].iloc[0]
    assert row['mean'] == row['median'] == .5
    assert row.std_population == .5
    assert row.mode_values == [0, 1] and row.mode_count == 2
    assert row['count'] == 4
    assert statistical_values(frame).temperature.isna().all()


def test_dedup_uses_last_inactive_without_erasing_raw_rows():
    frame = make_frame([3, 5], minutes=[0, 0])
    frame.loc[1, 'quality_status'] = 'inactive'
    frame.loc[1, 'bike_usable'] = False
    frame = mark_latest_slots(frame, SamplingCadence(300))
    assert len(frame) == 2 and frame.slot_latest.sum() == 1
    assert statistical_values(frame).available_bikes.isna().all()
    stations = [SimpleNamespace(station_id='001', name='Isolated test station')]
    result = missingness(frame, stations).iloc[0]
    assert result.duplicate_slot_rows == 1 and result.inactive_rows == 1


def test_daily_coverage_honors_mid_hour_cadence_transition():
    frame = make_frame([0] * 7, minutes=[0, 25, 30, 40, 45, 50, 55])
    plan = SamplingCadence(1800, CHANGES)
    frame = mark_latest_slots(frame, plan)
    options = AnalysisOptions(sampling_schedule=CHANGES)
    result = daily_coverage(frame, [SimpleNamespace(station_id='001', name='Test')],
        {'001': START}, plan, options, START, START + timedelta(hours=1)).iloc[0]
    assert result.expected_slots == 8 and result.usable_slots == 7
    assert result.coverage == 7 / 8 and result.missing_slots == 1
    assert result.partial_day


def test_zero_rain_is_valid_and_constant_correlation_is_undefined():
    frame = make_frame([1, 2, 3], weather=True)
    assert statistical_values(frame).rain.tolist() == [0, 0, 0]
    tables = correlation_tables(frame)
    assert tables['001']['pair_counts'].loc['rain', 'available_bikes'] == 3
    assert np.isnan(tables['001']['correlation'].loc['rain', 'available_bikes'])


def test_outliers_are_review_flags_and_changes_do_not_bridge_missing_slots():
    frame = make_frame([0, 30], minutes=[0, 10])
    assert outlier_flags(frame, SamplingCadence(300)).empty
    adjacent = make_frame([0, 30], minutes=[0, 5])
    flags = outlier_flags(adjacent, SamplingCadence(300))
    assert flags.reason.tolist() == ['large_adjacent_change']
    assert flags.action.tolist() == ['review_only_not_deleted']
    assert len(statistical_values(adjacent)) == 2
    capacity_flag = outlier_flags(make_frame([60]), SamplingCadence(300))
    assert capacity_flag.reason.tolist() == ['exceeds_current_capacity_snapshot']


def test_scalers_fit_only_train_and_preserve_missing_features():
    frame = make_frame(list(range(40)), weather=False)
    scaled, info = scaling_comparison(frame)
    train = scaled.loc[scaled.partition == 'train']
    assert info['parameters']['available_bikes']['max'] == train.available_bikes_raw.max()
    assert scaled.loc[scaled.partition == 'test', 'available_bikes_minmax'].max() > 1
    assert scaled.temperature_minmax.isna().all()
    assert not info['model_trained']
    assert (scaled.loc[scaled.partition == 'train', 'sampled_at'] + pd.Timedelta(minutes=30)
        < pd.Timestamp(info['validation_start_utc'])).all()
    assert len(scaled) == len(frame)  # Missing weather never drops the entire row.


def test_loader_filters_source_and_unfinished_publication(session, settings):
    from dataclasses import replace
    station = Station(source='citibike', station_id='001', name='Test only', latitude=40.75,
        longitude=-73.99, capacity=50, is_monitored=True, updated_at=START)
    session.add(station)
    for i, status in enumerate(['success', 'running']):
        run = CollectionRun(source='citibike', scheduled_at=START + timedelta(minutes=i * 5),
            started_at=START, finished_at=START + timedelta(seconds=10) if status == 'success' else None,
            status=status, success_count=1, error_count=0)
        session.add(run); session.flush()
        session.add(BikeObservation(source='citibike', station_id='001', collection_run_id=run.id,
            sampled_at=START + timedelta(minutes=i * 5), collected_at=START + timedelta(seconds=5),
            source_observed_at=START, quality_status='valid', available_bikes=0,
            is_installed=True, is_renting=True))
    session.commit()
    frame, _, _ = load_frame(session, replace(settings, station_ids=('001',)), AnalysisOptions(),
        START, START + timedelta(hours=1))
    assert len(frame) == 1 and frame.station_id.iloc[0] == '001'
    assert frame.available_bikes.iloc[0] == 0 and not frame.weather_usable.iloc[0]
    with pytest.raises(ValueError, match='row limit'):
        load_frame(session, replace(settings, station_ids=('001',)), AnalysisOptions(),
            START, START + timedelta(hours=1), max_rows=0)


def test_eda_loads_real_archive_but_excludes_estimates_and_keeps_live_priority(session,settings):
    from dataclasses import replace
    from shared.repositories.silver import bike_observations
    for source in ('citibike','citibike_historical','citibike_estimated'):
        session.add(Station(source=source,station_id='001',name='Test archive',latitude=40.75,
            longitude=-73.99,capacity=50,is_monitored=source=='citibike',updated_at=START))
        run=CollectionRun(source=source,scheduled_at=START,started_at=START,finished_at=START+timedelta(seconds=10),
            status='success',success_count=1,error_count=0)
        session.add(run);session.flush()
        at=START+timedelta(seconds=30 if source=='citibike_historical' else 0)
        session.add(BikeObservation(source=source,station_id='001',collection_run_id=run.id,
            sampled_at=at,collected_at=at,source_observed_at=at,available_bikes=9,
            quality_status='inactive' if source=='citibike' else 'valid',
            is_installed=True,is_renting=source!='citibike'))
    session.commit()
    frame,_,firsts=load_frame(session,replace(settings,station_ids=('001',)),AnalysisOptions(),START,START+timedelta(hours=1))
    assert set(frame.source)=={'citibike','citibike_historical'}
    assert firsts['001']==START
    frame=mark_latest_slots(frame,SamplingCadence(300))
    assert frame.loc[frame.slot_latest,'source'].tolist()==['citibike']
    assert statistical_values(frame).available_bikes.isna().all()
    # Shared live readers/ML do not silently broaden their source to include imports.
    assert len(list(session.scalars(bike_observations(source='citibike',include_unusable=True))))==1


def test_empty_report_strict_json_and_escaping(tmp_path):
    import json
    from eda.plots import generate_plots
    frame = make_frame([])
    values, info = scaling_comparison(frame)
    tables = {'descriptive': descriptive_statistics(frame), 'missingness': pd.DataFrame(),
        'coverage': pd.DataFrame(), 'outliers': outlier_flags(frame, SamplingCadence(300)),
        'correlations': correlation_tables(frame), 'scaled': values, 'scaling_info': info,
        **temporal_profiles(frame)}
    summary = {'source': '<script>bad</script>', 'window_start_local': 'start', 'cutoff_local': 'end',
        'generated_at_utc': START.isoformat(), 'raw_rows': 0, 'deduplicated_rows': 0,
        'usable_bike_rows': 0, 'usable_bikes_without_usable_weather': 0, 'outlier_flag_count': 0,
        'outlier_observation_count': 0, 'database_written': False}
    figures = generate_plots(frame, [], tables, SamplingCadence(300), tmp_path / 'figures')
    write_report(tmp_path, frame, tables, summary, figures)
    report = (tmp_path / 'report.html').read_text(encoding='utf-8')
    assert '<script>bad</script>' not in report and '&lt;script&gt;' in report
    assert 'NaN' not in (tmp_path / 'summary.json').read_text(encoding='utf-8')
    assert json.loads((tmp_path / 'summary.json').read_text(encoding='utf-8'))['database_written'] is False
    assert json_safe({'missing': float('nan'), 'zero': np.float64(0)}) == {'missing': None, 'zero': 0}


def test_vietnamese_table_preserves_source_fields_and_escapes_values():
    from eda.report import presentation_table
    frame = pd.DataFrame([{'station_id': '001', 'column': 'available_bikes',
        'mean': 0.0, 'reason': 'iqr_1_5', 'station_name': '<script>x</script>'}])
    original = frame.copy(deep=True)
    html = presentation_table(frame)
    assert 'Mã trạm' in html and 'Xe có thể thuê' in html and 'Trung bình' in html
    assert 'Ngoại lệ theo khoảng tứ phân vị' in html
    assert '<script>x</script>' not in html
    pd.testing.assert_frame_equal(frame, original)
