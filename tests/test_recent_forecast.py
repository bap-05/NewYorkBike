"""Recent day-ahead inputs must be causal, covered, bounded and source-scoped."""
from datetime import date, datetime, timedelta

import pytest

from eda.recent_forecast import adjusted_prediction, historical_issue, recent_inputs
from shared.cadence import SamplingCadence
from shared.time import UTC
from tests.test_eda import make_frame, START
from tests.test_time_patterns import NY

ISSUE = datetime(2026, 11, 23, 9, tzinfo=NY).astimezone(UTC)


def fixture():
    days = [ISSUE.astimezone(NY).date() - timedelta(days=i) for i in range(1, 36)]
    eligible = {day.isoformat() for day in days}
    known = {('001', day.isoformat(), hour): float(20 if day in days[:3] else 10)
        for day in days for hour in range(24)}
    timestamps = [ISSUE - timedelta(minutes=i) for i in range(180, 0, -5)]
    frame = make_frame([30 if at < ISSUE - timedelta(hours=1) else 36 for at in timestamps],
        [int((at - START).total_seconds() / 60) for at in timestamps])
    return frame, known, eligible


def test_recent_features_use_current_level_hourly_daily_and_weekly_changes():
    frame, known, eligible = fixture()
    result = recent_inputs(frame, known, eligible, '001', ISSUE, SamplingCadence(300))
    assert result['latest_bikes'] == 36
    assert result['recent_samples'] == 36
    assert result['recent_coverage'] >= .8
    assert result['hourly_trend'] == pytest.approx(6)
    assert result['daily_trend'] == 0
    assert result['weekly_shift'] == 10
    assert result['weekly_reference_days'] == 3
    assert result['latest_delta'] > 0 and result['recent_delta'] > 0


def test_future_collection_in_same_slot_cannot_erase_available_input():
    frame, known, eligible = fixture()
    expected = recent_inputs(frame, known, eligible, '001', ISSUE, SamplingCadence(300))
    later = frame.iloc[-1].copy()
    later['observation_id'] = 99999
    later['available_bikes'] = 999
    later['sampled_at'] += timedelta(minutes=1)
    later['collected_at'] = ISSUE + timedelta(seconds=1)
    import pandas as pd
    frame = pd.concat([frame, later.to_frame().T], ignore_index=True)
    for column in ('sampled_at','collected_at','source_observed_at'):
        frame[column] = pd.to_datetime(frame[column], utc=True)
    actual = recent_inputs(frame, known, eligible, '001', ISSUE, SamplingCadence(300))
    assert actual == expected


def test_unusable_latest_marker_blocks_recent_inputs():
    frame, known, eligible = fixture()
    frame.loc[frame.index[-1], 'bike_usable'] = False
    assert recent_inputs(frame, known, eligible, '001', ISSUE, SamplingCadence(300)) is None


def test_insufficient_window_allows_persistence_but_not_adaptive():
    frame, known, eligible = fixture()
    result = recent_inputs(frame.iloc[-2:], known, eligible, '001', ISSUE, SamplingCadence(300))
    assert result['recent_coverage'] < .8
    target = ISSUE + timedelta(hours=20)
    assert adjusted_prediction(10, result, 50, ISSUE, target, 'adaptive_recent') is None
    assert adjusted_prediction(10, result, 50, ISSUE, target, 'persistence') == 36


def test_adjustment_reacts_to_level_shift_and_damps_long_horizon():
    frame, known, eligible = fixture()
    inputs = recent_inputs(frame, known, eligible, '001', ISSUE, SamplingCadence(300))
    near = adjusted_prediction(10, inputs, 50, ISSUE, ISSUE + timedelta(hours=15), 'adaptive_recent')
    far = adjusted_prediction(10, inputs, 50, ISSUE, ISSUE + timedelta(hours=38), 'adaptive_recent')
    assert 10 < far < near <= 50
    assert adjusted_prediction(49, inputs, 50, ISSUE, ISSUE, 'adaptive_recent') == 50
    assert adjusted_prediction(10, None, 50, ISSUE, ISSUE, 'adaptive_recent') is None


def test_historical_issue_preserves_local_clock_across_dst():
    cutoff = datetime(2026, 11, 14, 14, 12, tzinfo=NY).astimezone(UTC)
    issue = historical_issue(date(2026, 10, 25), cutoff)
    assert issue.astimezone(NY).hour == 14
    assert issue.hour == 18  # EDT in October, despite EST at the live cutoff.


def test_combined_model_is_compared_but_not_forced_when_a_baseline_is_better():
    import math
    from eda.patterns import calendar_patterns
    from eda.weekday_forecast import update_forecasts
    from tests.test_time_patterns import hourly_fixture, STATION
    frame, coverage, cutoff = hourly_fixture(days=35)
    frame['available_bikes'] = frame.available_bikes.astype(float)
    days = sorted(coverage.local_date)
    for index, day in enumerate(days):
        mask = frame.local_date == day
        frame.loc[mask, 'available_bikes'] = frame.loc[mask, 'local_hour'].map(
            lambda hour: 10 + .5 * index + 6 * math.sin(hour * math.pi / 12))
    cadence = SamplingCadence(1800)
    patterns = calendar_patterns(frame, coverage, [STATION], cutoff, cadence)
    result = update_forecasts(frame, patterns['daily'], [STATION], cutoff, cadence,
        patterns['day_ahead']['items'])[0]
    scores = result['candidate_scores']
    assert scores['adaptive_recent']['validation']['samples'] > 0
    assert scores['adaptive_recent']['validation']['mae'] < scores['weekday']['validation']['mae']
    assert result['selected_model'] == 'seven_day'
    assert result['baseline_validation_mae'] < scores['adaptive_recent']['validation']['mae']


@pytest.mark.parametrize('preferred', ['adaptive_recent', 'seven_day'])
def test_live_trend_outage_uses_covered_calendar_instead_of_blank_forecast(monkeypatch, preferred):
    from eda import recent_forecast
    from eda.patterns import calendar_patterns
    from eda.weekday_forecast import update_forecasts, metrics as original_metrics
    from tests.test_time_patterns import hourly_fixture, STATION
    frame, coverage, cutoff = hourly_fixture(days=35)
    coverage.loc[coverage.local_date == (cutoff.astimezone(NY).date()-timedelta(days=1)).isoformat(), 'coverage'] = .1
    cadence = SamplingCadence(1800)
    patterns = calendar_patterns(frame, coverage, [STATION], cutoff, cadence)
    original_inputs = recent_forecast.recent_inputs
    def inputs(*args):
        value = original_inputs(*args)
        if args[4] == cutoff and value:
            value.update(recent_samples=1, recent_coverage=1/6, latest_delta=None, recent_delta=None)
        return value
    def metrics(rows, model):
        result = original_metrics(rows, model)
        if rows and model == preferred:
            result['mae'] = -1  # Force historical preference; live feasibility must still win.
        return result
    monkeypatch.setattr(recent_forecast, 'recent_inputs', inputs)
    monkeypatch.setattr('eda.weekday_forecast.metrics', metrics)
    result = update_forecasts(frame, patterns['daily'], [STATION], cutoff, cadence,
        patterns['day_ahead']['items'])[0]
    assert result['recent_inputs']['recent_samples'] == 1
    assert result['selected_model'] in ('weekday', 'day_type', 'seven_day')
    assert all(h['status'] == 'available' for h in result['hourly_forecasts'])
