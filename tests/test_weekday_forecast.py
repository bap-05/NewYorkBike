"""Calendar effects and temporal selection, using isolated synthetic fixtures only."""
from datetime import date, timedelta

import pytest

from eda.patterns import calendar_patterns
from eda.weekday_forecast import estimate, update_forecasts
from shared.cadence import SamplingCadence
from tests.test_time_patterns import hourly_fixture, STATION


def known_history(target, days=35):
    days = [target - timedelta(days=i) for i in range(2, days + 2)]
    history = {('001', d.isoformat(), 8): float(d.weekday() * 5) for d in days}
    return history, {d.isoformat() for d in days}


@pytest.mark.parametrize('target,expected', [('2026-11-23', 0), ('2026-11-28', 25)])
def test_same_weekday_distinguishes_monday_from_saturday(target, expected):
    target = date.fromisoformat(target)
    history, eligible = known_history(target)
    value, dates, method = estimate(history, eligible, '001', target, 8, 'weekday')
    assert value == expected and method == 'weekday'
    assert len(dates) >= 2
    assert all(date.fromisoformat(d).weekday() == target.weekday() for d in dates)
    old, _, _ = estimate(history, eligible, '001', target, 8, 'seven_day')
    assert old != value


def test_issue_day_and_target_day_are_never_used_even_if_present():
    target = date(2026, 11, 24)
    history, eligible = known_history(target)
    expected = estimate(history, eligible, '001', target, 8, 'day_type')
    for day in (target - timedelta(days=1), target, target + timedelta(days=1)):
        history[('001', day.isoformat(), 8)] = 10000
        eligible.add(day.isoformat())
    actual = estimate(history, eligible, '001', target, 8, 'day_type')
    assert actual == expected
    assert all(date.fromisoformat(d) < target - timedelta(days=1) for d in actual[1])


def test_weekday_falls_back_to_day_type_without_mixing_weekends():
    target = date(2026, 11, 23)
    history, eligible = known_history(target, days=7)
    value, dates, method = estimate(history, eligible, '001', target, 8, 'weekday')
    assert method == 'day_type'
    assert all(date.fromisoformat(d).weekday() < 5 for d in dates)
    assert value is not None


def test_insufficient_history_does_not_fabricate_an_hour():
    assert estimate({}, set(), '001', date(2026, 11, 23), 8, 'weekday')[0] is None


def test_later_labels_do_not_change_earlier_walk_forward_selections():
    frame, coverage, cutoff = hourly_fixture(days=35)
    for day_string in coverage.local_date:
        frame.loc[frame.local_date == day_string, 'available_bikes'] = (
            40 if date.fromisoformat(day_string).weekday() >= 5 else 5)
    cadence = SamplingCadence(1800)
    def calculate():
        patterns = calendar_patterns(frame, coverage, [STATION], cutoff, cadence)
        return update_forecasts(frame, patterns['daily'], [STATION], cutoff,
            cadence, patterns['day_ahead']['items'])[0]
    first = calculate()
    assert first['selected_model'] == 'weekday'
    assert first['test_mae'] < first['baseline_test_mae']
    assert first['selection_status'] == 'validated' and first['test_days'] >= 3
    for day_string in sorted(coverage.local_date)[-3:]:
        frame.loc[frame.local_date == day_string, 'available_bikes'] = 22
    second = calculate()
    earliest_change = sorted(coverage.local_date)[-3]
    before = [r for r in first['selection_history'] if r['target_date'] <= earliest_change]
    after = [r for r in second['selection_history'] if r['target_date'] <= earliest_change]
    assert before == after
    for selection in second['selection_history']:
        assert all(date.fromisoformat(d) < date.fromisoformat(selection['target_date']) - timedelta(days=1)
            for d in selection['validation_dates'])
    assert second['test_mae'] != first['test_mae']
