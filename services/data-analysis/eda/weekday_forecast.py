"""Weekday-aware hourly baselines, selected on past validation dates only."""
from datetime import date, datetime, time, timedelta
import math

from eda.dataset import statistical_values
from eda.hourly_forecast import hourly_history
from eda.patterns import ZONE, availability_class

MODELS = ('weekday', 'day_type', 'seven_day')
LABELS = {'weekday': 'Cùng thứ và cùng giờ', 'day_type': 'Cùng nhóm ngày và cùng giờ',
    'seven_day': 'Trung bình cùng giờ 7 ngày'}


def estimate(history, eligible, station_id, target, hour, model):
    """Target D is issued on D-1; only completed days strictly before D-1."""
    issue_day = target - timedelta(days=1)
    previous = [issue_day - timedelta(days=i) for i in range(1, 29)]
    valid = [(day, history[(station_id, day.isoformat(), hour)]) for day in previous
        if day.isoformat() in eligible and (station_id, day.isoformat(), hour) in history]
    if model == 'weekday':
        matches = [(day, value) for day, value in valid if day.weekday() == target.weekday()][:4]
        if len(matches) >= 2:
            return sum(v for _, v in matches) / len(matches), [d.isoformat() for d, _ in matches], 'weekday'
    if model in ('weekday', 'day_type'):
        matches = [(day, value) for day, value in valid
            if (day.weekday() >= 5) == (target.weekday() >= 5)][:10]
        if len(matches) >= 3:
            return sum(v for _, v in matches) / len(matches), [d.isoformat() for d, _ in matches], 'day_type'
    previous = previous[:7]
    values = [(day, value) for day, value in valid if day in previous]
    if all(day.isoformat() in eligible for day in previous) and len(values) >= 5:
        return sum(v for _, v in values) / len(values), [d.isoformat() for d, _ in values], 'seven_day'
    return None, [d.isoformat() for d, _ in valid], 'unavailable'


def metrics(rows, model):
    if not rows:
        return {'samples': 0, 'mae': None, 'rmse': None}
    errors = [row[model] - row['actual'] for row in rows]
    return {'samples': len(errors), 'mae': sum(abs(e) for e in errors) / len(errors),
        'rmse': math.sqrt(sum(e * e for e in errors) / len(errors))}


def update_forecasts(frame, daily, stations, cutoff, cadence, items):
    """Keep EDA's legacy snapshots intact; update only live API forecasts."""
    from eda.recent_forecast import (RECENT_MODELS, RECENT_LABELS, adjusted_prediction,
        historical_issue, recent_inputs)
    candidates = (*MODELS, *RECENT_MODELS)
    values = statistical_values(frame)
    base = frame.loc[values.index, ['station_id', 'local_date', 'local_hour', 'sampled_at']].copy()
    base['bikes'] = values.available_bikes
    known = hourly_history(base, daily, cadence)
    input_counts = base.groupby(['station_id', 'local_date', 'local_hour']).bikes.count().to_dict()
    by_id = {station.station_id: station for station in stations}
    today = cutoff.astimezone(ZONE).date()
    target = today + timedelta(days=1)
    for item in items:
        station = by_id[item['station_id']]
        eligible = set(daily.loc[(daily.station_id == station.station_id) & daily.eligible, 'local_date'])
        station_rows = frame.loc[frame.station_id == station.station_id]
        current_inputs = recent_inputs(station_rows, known, eligible, station.station_id, cutoff, cadence)
        samples = []
        if station.capacity is not None and station.capacity > 0:
            for day_string in sorted(eligible):
                day = date.fromisoformat(day_string)
                if day >= today:
                    continue
                issue = historical_issue(day, cutoff)
                inputs = recent_inputs(station_rows, known, eligible, station.station_id, issue, cadence)
                for hour in range(24):
                    actual = known.get((station.station_id, day_string, hour))
                    predictions = {model: estimate(known, eligible, station.station_id, day, hour, model)[0]
                        for model in MODELS}
                    target_at = datetime.combine(day, time(hour), ZONE).astimezone(cutoff.tzinfo)
                    predictions.update({model: adjusted_prediction(predictions['weekday'], inputs,
                        station.capacity, issue, target_at, model) for model in RECENT_MODELS})
                    # Compare candidates on identical dates/hours, never on different cohorts.
                    if actual is not None and all(v is not None for v in predictions.values()):
                        samples.append({'date': day_string, 'hour': hour, 'actual': actual,
                            **{m: min(float(station.capacity), max(0., p)) for m, p in predictions.items()}})
        dates = sorted({row['date'] for row in samples})
        selected, validation, test, selection_history = 'weekday', [], [], []
        if len(dates) >= 6:
            # For the next live forecast, all completed past dates are now known.
            # Select on the latest three, rather than freezing an outdated choice.
            validation = [row for row in samples if row['date'] in dates[-3:]]
            selected = min(candidates, key=lambda m: metrics(validation, m)['mae'])
            for day_string in dates[len(dates) // 2:]:
                issue_day = date.fromisoformat(day_string) - timedelta(days=1)
                prior_dates = [d for d in dates if date.fromisoformat(d) < issue_day][-3:]
                if len(prior_dates) < 3:
                    continue
                past_validation = [r for r in samples if r['date'] in prior_dates]
                choice = min(candidates, key=lambda m: metrics(past_validation, m)['mae'])
                selection_history.append({'target_date': day_string, 'model': choice,
                    'validation_dates': prior_dates})
                test.extend({**r, 'selected': r[choice]} for r in samples if r['date'] == day_string)
        labels = {**LABELS, **RECENT_LABELS}
        item.update(selected_model=selected, model_label=labels[selected],
            recent_inputs=current_inputs,
            selection_history=selection_history,
            candidate_scores={model: {'validation': metrics(validation, model), 'test': metrics(test, model)}
                for model in candidates},
            selection_status='validated' if validation else 'insufficient_validation',
            validation_days=len({r['date'] for r in validation}),
            test_days=len({r['date'] for r in test}),
            validation_mae=metrics(validation, selected)['mae'],
            baseline_validation_mae=metrics(validation, 'seven_day')['mae'],
            test_mae=metrics(test, 'selected')['mae'], test_rmse=metrics(test, 'selected')['rmse'],
            baseline_test_mae=metrics(test, 'seven_day')['mae'],
            baseline_test_rmse=metrics(test, 'seven_day')['rmse'],
            persistence_test_mae=metrics(test, 'persistence')['mae'],
            persistence_test_rmse=metrics(test, 'persistence')['rmse'])
        safety_reason = item['reason'] if item['reason'] in (
            'missing_capacity', 'inactive_or_unusable_latest_observation', 'stale_observation') else None
        for hour in item['hourly_forecasts']:
            value, support, method = estimate(known, eligible, station.station_id, target,
                hour['local_hour'], 'weekday' if selected in RECENT_MODELS else selected)
            seasonal_value = value
            if selected in RECENT_MODELS:
                value = adjusted_prediction(value, current_inputs, station.capacity, cutoff,
                    datetime.fromisoformat(hour['target_start_utc']), selected)
                method = selected
                if selected == 'persistence':
                    support = []
            reason = safety_reason or (('recent_inputs_unavailable' if selected in RECENT_MODELS
                else 'too_few_calendar_matches') if value is None else None)
            value = min(float(station.capacity), max(0., value)) if reason is None else None
            observed = [row for row in test if row['hour'] == hour['local_hour']]
            ready = len({r['date'] for r in observed}) >= 3
            score = metrics(observed, 'selected')
            correct = sum(availability_class(r['selected'], station.capacity)
                == availability_class(r['actual'], station.capacity) for r in observed) if ready else 0
            hour.update(predicted_mean_bikes=value, status='available' if value is not None else 'insufficient_data',
                reason=reason, history_days=len(support), forecast_method=method, support_dates=support,
                seasonal_bikes=seasonal_value,
                recent_adjustment=value - seasonal_value if value is not None and seasonal_value is not None else None,
                availability_class=availability_class(value, station.capacity) if value is not None else None,
                uses_estimated_data=False, input_estimated_samples=0,
                input_actual_samples=sum(int(input_counts.get((station.station_id, day, hour['local_hour']), 0))
                    for day in support),
                evaluation_samples=len(observed), evaluation_status='available' if ready else 'insufficient_data',
                mae=score['mae'] if ready else None, rmse=score['rmse'] if ready else None,
                classification_accuracy=correct / len(observed) if ready else None)
        available = [h for h in item['hourly_forecasts'] if h['status'] == 'available']
        item.update(status='available' if available else 'insufficient_data',
            reason=None if available else safety_reason or 'too_few_calendar_matches',
            predicted_mean_bikes=sum(h['predicted_mean_bikes'] for h in available) / len(available) if available else None,
            low_bike_hours=[h['target_start_utc'] for h in available if h['availability_class'] == 'low'])
        item['availability_class'] = availability_class(item['predicted_mean_bikes'], station.capacity) if available else None
        # Station-level evaluation uses the same held-out hourly cohort as the charts.
        item.update(evaluation_samples=len(test), evaluation_status='available' if len(dates) >= 6 else 'insufficient_data',
            mae=item['test_mae'], rmse=item['test_rmse'],
            classification_accuracy=sum(availability_class(r['selected'], station.capacity)
                == availability_class(r['actual'], station.capacity) for r in test) / len(test) if test else None)
        confidence_reasons = []
        if item['test_days'] < 7:
            confidence_reasons.append('limited_test_history')
        if station.capacity and item['test_mae'] is not None and item['test_mae'] > station.capacity * .2:
            confidence_reasons.append('high_backtest_error')
        if (current_inputs and current_inputs['recent_delta'] is not None and station.capacity
                and abs(current_inputs['recent_delta']) > station.capacity * .3):
            confidence_reasons.append('large_recent_shift')
        item.update(confidence='low' if confidence_reasons else 'limited', confidence_reasons=confidence_reasons)
    return items
