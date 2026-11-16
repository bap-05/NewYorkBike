"""Day-ahead hourly seasonal baseline; preserve missing hours and UTC identities."""
from collections import Counter
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from shared.cadence import SamplingCadence
from shared.time import UTC

ZONE = ZoneInfo('America/New_York')


def hourly_history(base, daily, cadence):
    """Accept an hour only with >=80% of its scheduled valid observations."""
    if base.empty:
        return {}
    first = datetime.fromisoformat(base.local_date.min()).replace(tzinfo=ZONE)
    last = datetime.fromisoformat(base.local_date.max()).replace(tzinfo=ZONE) + timedelta(days=1)
    expected = Counter((tick.astimezone(ZONE).date().isoformat(), tick.astimezone(ZONE).hour)
        for tick in cadence.slots(first.astimezone(UTC), last.astimezone(UTC)))
    allowed = set(zip(daily.loc[daily.eligible, 'station_id'], daily.loc[daily.eligible, 'local_date']))
    history = {}
    for (station, date, hour), rows in base.groupby(['station_id', 'local_date', 'local_hour']):
        values = rows.bikes.dropna()
        required = expected[(date, int(hour))]
        if (station, date) in allowed and required and len(values) / required >= .8:
            history[(station, date, int(hour))] = float(values.mean())
    return history


def forecast_hours(base, daily, station, today, start, end, common_reason, cadence=None, *, live_base=None, live_daily=None):
    from eda.patterns import availability_class
    cadence = cadence or SamplingCadence(1800)
    known = hourly_history(base.loc[base.station_id == station.station_id],
        daily.loc[daily.station_id == station.station_id], cadence)
    eligible_dates = set(daily.loc[(daily.station_id == station.station_id) & daily.eligible, 'local_date'])
    live_base = base if live_base is None else live_base
    live_daily = daily if live_daily is None else live_daily
    live_known = hourly_history(live_base.loc[live_base.station_id == station.station_id],
        live_daily.loc[live_daily.station_id == station.station_id], cadence)
    live_dates = set(live_daily.loc[(live_daily.station_id == station.station_id) & live_daily.eligible,'local_date'])

    def estimate(date, hour, *, input_history=None, input_dates=None):
        input_history = known if input_history is None else input_history
        input_dates = eligible_dates if input_dates is None else input_dates
        previous = [(date - timedelta(days=i)).isoformat() for i in range(1, 8)]
        values = [input_history[(station.station_id, day, hour)] for day in previous
            if (station.station_id, day, hour) in input_history]
        if not all(day in input_dates for day in previous):
            return None, len(values)
        if len(values) < 5 or station.capacity is None or station.capacity <= 0:
            return None, len(values)
        return min(float(station.capacity), max(0., float(np.mean(values)))), len(values)

    evaluation = {}
    for hour in range(24):
        errors, correct = [], 0
        for date_string in sorted(eligible_dates):
            actual = known.get((station.station_id, date_string, hour))
            # Serving tomorrow excludes the still-incomplete day of issuance.
            # Replay that same one-day lead time; never use target-1 as a completed day.
            issued_day = datetime.fromisoformat(date_string).date() - timedelta(days=1)
            predicted, _ = estimate(issued_day, hour)
            if actual is None or predicted is None:
                continue
            errors.append(predicted - actual)
            correct += availability_class(predicted, station.capacity) == availability_class(actual, station.capacity)
        enough = len(errors) >= 3
        evaluation[hour] = {'evaluation_samples': len(errors),
            'evaluation_status': 'available' if enough else 'insufficient_data',
            'mae': float(np.mean(np.abs(errors))) if enough else None,
            'rmse': float(np.sqrt(np.mean(np.square(errors)))) if enough else None,
            'classification_accuracy': correct / len(errors) if enough else None}

    results, cursor = [], start.astimezone(UTC)
    while cursor < end.astimezone(UTC):
        local = cursor.astimezone(ZONE)
        value, count = estimate(today, local.hour, input_history=live_known, input_dates=live_dates)
        previous = {(today-timedelta(days=i)).isoformat() for i in range(1,8)}
        support_dates = {day for day in previous if (station.station_id,day,local.hour) in live_known}
        cohort = live_base.loc[(live_base.station_id == station.station_id)
            & live_base.local_date.isin(support_dates) & (live_base.local_hour == local.hour) & live_base.bikes.notna()]
        estimated_count = int(cohort.is_estimated.sum()) if 'is_estimated' in cohort else 0
        reason = common_reason or ('too_few_matching_hours' if value is None else None)
        if reason:
            value = None
        results.append({'target_start_utc': cursor.isoformat(),
            'target_end_utc': (cursor + timedelta(hours=1)).isoformat(),
            'local_hour': local.hour, 'hour_label': f'{local:%H:%M} ({local:%z})',
            'status': 'available' if value is not None else 'insufficient_data', 'reason': reason,
            'history_days': count, 'predicted_mean_bikes': value,
            'uses_estimated_data': estimated_count > 0, 'input_estimated_samples': estimated_count,
            'input_actual_samples': len(cohort)-estimated_count,
            'availability_class': availability_class(value, station.capacity) if value is not None else None,
            **evaluation[local.hour]})
        cursor += timedelta(hours=1)
    return results
