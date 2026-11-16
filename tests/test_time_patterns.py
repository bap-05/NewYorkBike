"""Isolated calendar fixtures; never write synthetic data to an application database."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from eda.patterns import availability_class, calendar_patterns
from tests.test_eda import make_frame, START
from shared.time import UTC

STATION = SimpleNamespace(station_id='001', name='Isolated test station', capacity=50)
NY = ZoneInfo('America/New_York')


def history(days=10):
    begin = datetime(2026, 11, 9, tzinfo=NY)
    cutoff = (begin + timedelta(days=days, hours=9)).astimezone(UTC)
    counts, minutes, coverage = [], [], []
    for day in range(days):
        at = begin + timedelta(days=day)
        for hour in (0, 12):
            counts.append(day + 1)
            minutes.append(int(((at + timedelta(hours=hour)).astimezone(UTC) - START).total_seconds() / 60))
        coverage.append({'station_id': '001', 'local_date': at.date().isoformat(),
                         'coverage': 1., 'partial_day': False})
    counts.append(49)
    minutes.append(int((cutoff - timedelta(minutes=1) - START).total_seconds() / 60))
    return make_frame(counts, minutes), pd.DataFrame(coverage), cutoff


def test_day_ahead_uses_previous_days_not_current_day_and_walk_forward_evaluation():
    frame, coverage, cutoff = history()
    result = calendar_patterns(frame, coverage, [STATION], cutoff)
    item = result['day_ahead']['items'][0]
    assert item['status'] == 'available'
    assert item['predicted_mean_bikes'] == 7  # Mean of days 4..10; today's 49 excluded.
    assert item['target_date'] == '2026-11-20'
    assert item['availability_class'] == 'low'
    assert item['evaluation_samples'] == 3
    assert item['mae'] == item['rmse'] == 4
    assert not result['daily'].loc[result['daily'].local_date == '2026-11-19', 'eligible'].any()


def test_missing_day_blocks_forecast_and_incomplete_week_does_not_become_zero():
    frame, coverage, cutoff = history()
    coverage.loc[coverage.local_date == '2026-11-15', 'coverage'] = .5
    result = calendar_patterns(frame, coverage, [STATION], cutoff)
    item = result['day_ahead']['items'][0]
    assert item['reason'] == 'requires_seven_covered_completed_days'
    assert item['predicted_mean_bikes'] is None and item['availability_class'] is None
    assert result['weekly'].mean_bikes.isna().all()


def test_stale_or_inactive_input_cannot_publish_forecast():
    frame, coverage, cutoff = history()
    assert calendar_patterns(frame, coverage, [STATION], cutoff + timedelta(hours=1))['day_ahead']['items'][0]['reason'] == 'stale_observation'
    frame.loc[frame.index[-1], 'bike_usable'] = False
    assert calendar_patterns(frame, coverage, [STATION], cutoff)['day_ahead']['items'][0]['predicted_mean_bikes'] is None


@pytest.mark.parametrize('date,hours', [('2026-03-07', 23), ('2026-10-31', 25)])
def test_tomorrow_uses_calendar_day_across_dst(date, hours):
    cutoff = datetime.fromisoformat(date).replace(tzinfo=NY).astimezone(UTC)
    item = calendar_patterns(make_frame([]), pd.DataFrame(), [STATION], cutoff)['day_ahead']['items'][0]
    elapsed = datetime.fromisoformat(item['target_end_utc']) - datetime.fromisoformat(item['target_start_utc'])
    assert elapsed.total_seconds() == hours * 3600
    assert len(item['hourly_forecasts']) == hours
    assert len({h['target_start_utc'] for h in item['hourly_forecasts']}) == hours
    if hours == 25:
        repeated = [h for h in item['hourly_forecasts'] if h['local_hour'] == 1]
        assert len(repeated) == 2 and repeated[0]['hour_label'] != repeated[1]['hour_label']


def hourly_fixture(days=11):
    begin = datetime(2026, 11, 9, tzinfo=NY)
    cutoff = (begin + timedelta(days=days, hours=9)).astimezone(UTC)
    counts, minutes, coverage = [], [], []
    for day in range(days):
        date = begin + timedelta(days=day)
        for minute in range(0, 1440, 30):
            hour = minute // 60
            counts.append(0 if hour == 8 else 45 if hour == 18 else 25)
            minutes.append(int(((date + timedelta(minutes=minute)).astimezone(UTC) - START).total_seconds() / 60))
        coverage.append({'station_id': '001', 'local_date': date.date().isoformat(), 'coverage': 1., 'partial_day': False})
    counts.append(49)
    minutes.append(int((cutoff - timedelta(minutes=1) - START).total_seconds() / 60))
    return make_frame(counts, minutes), pd.DataFrame(coverage), cutoff


def test_matching_hour_preserves_low_and_high_patterns_instead_of_daily_average():
    from shared.cadence import SamplingCadence
    frame, coverage, cutoff = hourly_fixture()
    item = calendar_patterns(frame, coverage, [STATION], cutoff, SamplingCadence(1800))['day_ahead']['items'][0]
    assert len(item['hourly_forecasts']) == 24
    morning = next(h for h in item['hourly_forecasts'] if h['local_hour'] == 8)
    evening = next(h for h in item['hourly_forecasts'] if h['local_hour'] == 18)
    assert morning['predicted_mean_bikes'] == 0 and morning['availability_class'] == 'low'
    assert evening['predicted_mean_bikes'] == 45 and evening['availability_class'] == 'high'
    assert morning['history_days'] == 7
    assert morning['evaluation_samples'] == 3 and morning['mae'] == 0
    assert item['low_bike_hours'] == [morning['target_start_utc']]


def test_hourly_evaluation_replays_tomorrow_lead_time_without_incomplete_issue_day():
    from shared.cadence import SamplingCadence
    frame, coverage, cutoff = hourly_fixture()
    for index, day in enumerate(sorted(coverage.local_date)):
        frame.loc[frame.local_date == day, 'available_bikes'] = index + 1
    item = calendar_patterns(frame, coverage, [STATION], cutoff, SamplingCadence(1800))['day_ahead']['items'][0]
    hour = next(h for h in item['hourly_forecasts'] if h['local_hour'] == 8)
    assert hour['evaluation_samples'] == 3
    # Target days 9..11 use days 1..7, 2..8, 3..9 (not the day of issuance).
    assert hour['mae'] == hour['rmse'] == 5


def test_hourly_evaluation_does_not_publish_scores_before_three_test_days():
    from shared.cadence import SamplingCadence
    frame, coverage, cutoff = hourly_fixture(days=10)
    item = calendar_patterns(frame, coverage, [STATION], cutoff, SamplingCadence(1800))['day_ahead']['items'][0]
    hour = next(h for h in item['hourly_forecasts'] if h['local_hour'] == 8)
    assert hour['evaluation_samples'] == 2
    assert hour['evaluation_status'] == 'insufficient_data'
    assert hour['mae'] is None and hour['rmse'] is None and hour['classification_accuracy'] is None


def test_incomplete_seven_day_window_keeps_real_hour_support_count():
    from shared.cadence import SamplingCadence
    frame, coverage, cutoff = hourly_fixture()
    coverage.loc[coverage.local_date == '2026-11-15', 'coverage'] = .58
    item = calendar_patterns(frame, coverage, [STATION], cutoff, SamplingCadence(1800))['day_ahead']['items'][0]
    assert item['qualified_days'] == 6
    assert item['reason'] == 'requires_seven_covered_completed_days'
    hour = next(h for h in item['hourly_forecasts'] if h['local_hour'] == 8)
    assert hour['history_days'] == 6
    assert hour['predicted_mean_bikes'] is None  # Preserve the existing quality threshold.


def test_missing_matching_hours_stay_unavailable_without_filling_daily_mean():
    from shared.cadence import SamplingCadence
    frame, coverage, cutoff = hourly_fixture()
    missing = (frame.local_hour == 8) & frame.local_date.isin(['2026-11-13', '2026-11-14', '2026-11-15'])
    frame = frame.loc[~missing].copy()
    item = calendar_patterns(frame, coverage, [STATION], cutoff, SamplingCadence(1800))['day_ahead']['items'][0]
    hour = next(h for h in item['hourly_forecasts'] if h['local_hour'] == 8)
    assert hour['history_days'] == 4
    assert hour['reason'] == 'too_few_matching_hours'
    assert hour['predicted_mean_bikes'] is None and hour['availability_class'] is None
    assert item['low_bike_hours'] == []


def test_daily_mean_gives_hours_equal_weight_despite_different_sampling_rates():
    frame = make_frame([0] + [24] * 12, [-360] + list(range(360, 420, 5)))
    coverage = pd.DataFrame([{'station_id': '001', 'local_date': '2026-11-09', 'coverage': 1., 'partial_day': False}])
    result = calendar_patterns(frame, coverage, [STATION], datetime(2026, 11, 10, 14, tzinfo=UTC))
    assert result['daily'].mean_bikes.iloc[0] == 12


def test_classification_boundaries():
    assert availability_class(10, 50) == 'low'
    assert availability_class(40, 50) == 'high'
    assert availability_class(25, 50) == 'balanced'


def test_marked_estimates_enable_live_forecast_without_becoming_scoring_targets():
    from shared.cadence import SamplingCadence
    frame,coverage,cutoff=hourly_fixture()
    mask=(frame.local_date=='2026-11-15') & (frame.local_hour<12)
    estimates=frame.loc[mask,['station_id','sampled_at','available_bikes']].rename(columns={'available_bikes':'bikes'}).copy()
    estimates['is_estimated']=True
    frame=frame.loc[~mask].copy()
    coverage.loc[coverage.local_date=='2026-11-15','coverage']=.5
    original=frame.copy(deep=True)
    real_only=calendar_patterns(frame,coverage,[STATION],cutoff,SamplingCadence(1800))['day_ahead']['items'][0]
    supplemented=calendar_patterns(frame,coverage,[STATION],cutoff,SamplingCadence(1800),estimates)['day_ahead']['items'][0]
    assert real_only['reason']=='requires_seven_covered_completed_days'
    assert supplemented['status']=='available' and supplemented['qualified_days']==7
    assert supplemented['actual_qualified_days']==6
    assert supplemented['uses_estimated_data'] is True
    assert supplemented['input_estimated_samples']==24
    assert all(hour['status']=='available' for hour in supplemented['hourly_forecasts'])
    for original_hour,filled_hour in zip(real_only['hourly_forecasts'],supplemented['hourly_forecasts']):
        for field in ('evaluation_samples','mae','rmse','classification_accuracy'):
            assert original_hour[field]==filled_hour[field]
    pd.testing.assert_frame_equal(frame,original)


def test_estimated_row_never_overrides_existing_real_observation():
    from shared.cadence import SamplingCadence
    frame,coverage,cutoff=hourly_fixture()
    original=calendar_patterns(frame,coverage,[STATION],cutoff,SamplingCadence(1800))['day_ahead']['items'][0]
    estimates=frame.loc[frame.local_hour==8,['station_id','sampled_at','available_bikes']].rename(columns={'available_bikes':'bikes'}).copy()
    estimates['bikes']=50
    estimates['is_estimated']=True
    supplemented=calendar_patterns(frame,coverage,[STATION],cutoff,SamplingCadence(1800),estimates)['day_ahead']['items'][0]
    assert supplemented['uses_estimated_data'] is False
    assert supplemented['predicted_mean_bikes']==original['predicted_mean_bikes']
    assert next(h for h in supplemented['hourly_forecasts'] if h['local_hour']==8)['predicted_mean_bikes']==0
