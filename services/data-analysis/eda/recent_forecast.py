"""Causal level/trend adjustments for next-day calendar forecasts; no source calls."""
from datetime import datetime, time, timedelta
import math

import pandas as pd

from eda.patterns import ZONE
from eda.weekday_forecast import estimate
from shared.time import UTC

RECENT_MODELS = ('adaptive_recent', 'adaptive_balanced', 'persistence')
RECENT_LABELS = {
    'adaptive_recent': 'Theo thứ/giờ, mức xe và xu hướng gần đây',
    'adaptive_balanced': 'Theo thứ/giờ, điều chỉnh thận trọng theo xu hướng',
    'persistence': 'Giữ nguyên số xe mới nhất',
}


def historical_issue(target_day, cutoff):
    """Replay the same local issue time on D-1, respecting NY DST."""
    local = cutoff.astimezone(ZONE)
    clock = time(local.hour, local.minute, local.second, local.microsecond, fold=local.fold)
    return datetime.combine(target_day - timedelta(days=1), clock, ZONE).astimezone(UTC)


def recent_inputs(rows, known, eligible, station_id, issue, cadence):
    # Include today's partial observations, but nothing collected after issuance.
    past = rows.loc[(rows.sampled_at <= issue) & (rows.collected_at <= issue)].copy()
    # Re-deduplicate at the historical issue instant, not at today's cutoff:
    # a later observation in the same slot must not hide an earlier available one.
    past['_priority'] = past.source.ne('citibike_historical').astype(int)
    past = past.sort_values(['_priority', 'sampled_at', 'collected_at', 'observation_id'])
    if 'slot_utc' in past:
        past = past.drop_duplicates('slot_utc', keep='last')
    past = past.sort_values('sampled_at')
    if past.empty:
        return None
    latest = past.iloc[-1]
    if (not latest.bike_usable or pd.isna(latest.source_observed_at)
            or not 0 <= (issue - latest.source_observed_at).total_seconds() <= 600):
        return None
    issue_day = issue.astimezone(ZONE).date()
    latest_bikes = float(latest.available_bikes)
    three_hours = past.loc[past.sampled_at >= issue - timedelta(hours=3)]
    expected = sum(1 for _ in cadence.slots(issue - timedelta(hours=3), issue + timedelta(microseconds=1)))
    valid = three_hours.loc[three_hours.bike_usable & (three_hours.source_observed_at <= issue)]
    complete = expected > 0 and len(valid) / expected >= .8
    result = {'latest_bikes': latest_bikes, 'latest_at': latest.sampled_at.isoformat(),
        'recent_samples': len(valid), 'recent_coverage': min(1., len(valid) / expected) if expected else 0.,
        'latest_delta': None, 'recent_delta': None, 'hourly_trend': None,
        'daily_trend': None, 'weekly_shift': None, 'weekly_reference_days': 0,
        'recent_mean_bikes': float(valid.available_bikes.mean()) if len(valid) else None}
    # Persistence can be compared even when trend windows are not covered.
    if not complete:
        return result
    residuals = []
    references = {}
    for row in valid.itertuples():
        local = row.sampled_at.to_pydatetime().astimezone(ZONE)
        key = (local.date(), local.hour)
        if key not in references:
            references[key] = estimate(known, eligible, station_id, local.date(), local.hour, 'weekday')[0]
        reference = references[key]
        if reference is not None:
            residuals.append((row.sampled_at.to_pydatetime(), float(row.available_bikes) - reference))
    local_latest = latest.sampled_at.to_pydatetime().astimezone(ZONE)
    reference = references.get((local_latest.date(), local_latest.hour))
    if reference is None or len(residuals) < .8 * expected:
        return result
    recent = [v for _, v in residuals]
    last_hour = [v for at, v in residuals if at >= issue - timedelta(hours=1)]
    earlier = [v for at, v in residuals if at < issue - timedelta(hours=1)]
    means = {}
    for day in [issue_day - timedelta(days=i) for i in range(1, 11)]:
        values = [known[(station_id, day.isoformat(), hour)] for hour in range(24)
            if (station_id, day.isoformat(), hour) in known and day.isoformat() in eligible]
        if values:
            means[day] = sum(values) / len(values)
    recent_days = [issue_day - timedelta(days=i) for i in range(1, 4)]
    weekly_changes = [means[day] - means[day - timedelta(days=7)] for day in recent_days
        if day in means and day - timedelta(days=7) in means]
    recent_means = [(day, means[day]) for day in recent_days if day in means]
    result.update(latest_delta=latest_bikes - reference,
        recent_delta=sum(recent) / len(recent),
        hourly_trend=(sum(last_hour) / len(last_hour) - sum(earlier) / len(earlier)) if last_hour and earlier else None,
        daily_trend=(recent_means[0][1] - recent_means[-1][1])
            / (recent_means[0][0] - recent_means[-1][0]).days if len(recent_means) >= 2 else None,
        weekly_shift=sum(weekly_changes) / len(weekly_changes) if weekly_changes else None,
        weekly_reference_days=len(weekly_changes))
    return result


def adjusted_prediction(calendar_value, inputs, capacity, issue, target_at, model):
    if inputs is None or capacity is None or capacity <= 0:
        return None
    if model == 'persistence':
        return min(float(capacity), max(0., inputs['latest_bikes']))
    if calendar_value is None or inputs['latest_delta'] is None or inputs['recent_delta'] is None:
        return None
    # Missing daily/weekly references stay explicitly missing in public metadata.
    # Redistribute their weight rather than fabricating a zero change.
    offsets = [(inputs['latest_delta'], .4), (inputs['recent_delta'], .4)]
    if inputs['weekly_shift'] is not None:
        offsets.append((inputs['weekly_shift'], .2))
    offset = sum(v * w for v, w in offsets) / sum(w for _, w in offsets)
    trend = .15 * (inputs['hourly_trend'] or 0.) + .1 * (inputs['daily_trend'] or 0.)
    # Damp, bound, and never linearly extrapolate a short trend over an entire day.
    trend = max(-capacity * .1, min(capacity * .1, trend))
    horizon = max(0., (target_at - issue).total_seconds() / 3600)
    strength, lifetime = (1., 48.) if model == 'adaptive_recent' else (.5, 24.)
    value = calendar_value + strength * math.exp(-horizon / lifetime) * (offset + trend)
    return min(float(capacity), max(0., value))
