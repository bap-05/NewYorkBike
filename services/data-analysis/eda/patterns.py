"""Calendar-aware time-series patterns and an explicitly labelled day-ahead baseline.

All estimates use published history before cutoff; no source calls or database writes.
Hourly estimates give each historical day equal weight, so the change from 30 to
5 minutes does not multiply the importance of recent days. The next-day target
is hourly mean rentable bikes, not trip demand or the existing +30-minute forecast.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from eda.dataset import statistical_values
from shared.time import UTC

ZONE = ZoneInfo('America/New_York')
CLASS_LABELS = {'low': 'Ít xe', 'balanced': 'Mức trung bình', 'high': 'Nhiều xe'}


def availability_class(value, capacity):
    ratio = value / capacity
    return 'low' if ratio <= .2 else 'high' if ratio >= .8 else 'balanced'


def calendar_aggregates(frame, coverage, cutoff):
    """Calendar means only: reusable by read-only APIs without forecasting."""
    cutoff = pd.Timestamp(cutoff).to_pydatetime().astimezone(UTC)
    today = cutoff.astimezone(ZONE).date()
    values = statistical_values(frame)
    base = frame.loc[values.index, ['station_id', 'local_date', 'local_hour', 'sampled_at']].copy()
    base['bikes'] = values.available_bikes
    # Reject late/future rows even if a caller passes an unfiltered fixture.
    base = base.loc[base.sampled_at < cutoff]
    hourly = base.groupby(['station_id', 'local_date', 'local_hour']).bikes.mean()
    daily = hourly.groupby(['station_id', 'local_date']).mean().rename('mean_bikes').reset_index()
    if not coverage.empty:
        daily = daily.merge(coverage[['station_id', 'local_date', 'coverage', 'partial_day']],
            on=['station_id', 'local_date'], how='left', validate='one_to_one')
    else:
        daily['coverage'], daily['partial_day'] = np.nan, True
    daily['eligible'] = ((daily.coverage >= .8) & ~daily.partial_day.fillna(True).astype(bool)
        & (daily.local_date < today.isoformat()) & daily.mean_bikes.notna())
    daily['date'] = pd.to_datetime(daily.local_date)
    daily['week'] = daily.date.dt.to_period('W-SUN').astype(str)
    daily['month'] = daily.date.dt.to_period('M').astype(str)
    weekly, monthly = [], []
    for field, target in [('week', weekly), ('month', monthly)]:
        for (station_id, period), rows in daily.groupby(['station_id', field]):
            count = int(rows.eligible.sum())
            required = 7 if field == 'week' else pd.Period(period, freq='M').days_in_month
            target.append({'station_id': station_id, 'period': period,
                'eligible_days': count, 'expected_days': required,
                'complete': count == required,
                'mean_bikes': float(rows.loc[rows.eligible, 'mean_bikes'].mean()) if count == required else None})
    return {'daily': daily, 'weekly': pd.DataFrame(weekly), 'monthly': pd.DataFrame(monthly)}


def calendar_patterns(frame, coverage, stations, cutoff, cadence=None, forecast_estimates=None):
    """Return quality-gated daily/weekly/monthly means and next-day estimates."""
    cutoff = pd.Timestamp(cutoff).to_pydatetime().astimezone(UTC)
    today = cutoff.astimezone(ZONE).date()
    tables = calendar_aggregates(frame, coverage, cutoff)
    daily = tables['daily']
    values = statistical_values(frame)
    base = frame.loc[values.index, ['station_id', 'local_date', 'local_hour', 'sampled_at']].copy()
    base['bikes'] = values.available_bikes
    base = base.loc[base.sampled_at < cutoff]
    target_date = today + timedelta(days=1)
    target_start = datetime.combine(target_date, time.min, ZONE)
    target_end = datetime.combine(target_date + timedelta(days=1), time.min, ZONE)
    forecasts = []
    from eda.hourly_forecast import forecast_hours
    from eda.forecast_inputs import live_forecast_history
    from shared.cadence import SamplingCadence
    cadence = cadence or SamplingCadence(1800)
    live_base, live_daily = live_forecast_history(base, daily, frame, coverage,
        forecast_estimates, cadence, cutoff)
    for station in stations:
        rows = daily.loc[(daily.station_id == station.station_id) & daily.eligible]
        expected_days = [(today - timedelta(days=i)).isoformat() for i in range(1, 8)]
        history = rows.loc[rows.local_date.isin(expected_days)]
        live_history = live_daily.loc[(live_daily.station_id == station.station_id)
            & live_daily.eligible & live_daily.local_date.isin(expected_days)]
        input_rows = live_base.loc[(live_base.station_id == station.station_id)
            & live_base.local_date.isin(expected_days) & live_base.bikes.notna()]
        estimated_samples = int(input_rows.is_estimated.sum())
        actual_samples = len(input_rows) - estimated_samples
        observed = frame.loc[(frame.station_id == station.station_id) & frame.slot_latest
            & (frame.sampled_at < cutoff)].sort_values('sampled_at')
        latest = observed.iloc[-1] if len(observed) else None
        reason = None
        if station.capacity is None or station.capacity <= 0:
            reason = 'missing_capacity'
        elif latest is None or not latest.bike_usable:
            reason = 'inactive_or_unusable_latest_observation'
        elif pd.isna(latest.source_observed_at) or not 0 <= (cutoff - latest.source_observed_at).total_seconds() <= 600:
            reason = 'stale_observation'
        elif len(live_history) != 7:
            reason = 'requires_seven_covered_completed_days'
        estimate = min(float(station.capacity), max(0., float(live_history.mean_bikes.mean()))) if reason is None else None
        # Walk-forward evaluation: each historical target uses only its previous seven days.
        errors, correct = [], 0
        for row in rows.itertuples():
            date = datetime.fromisoformat(row.local_date).date()
            prior_dates = [(date - timedelta(days=i)).isoformat() for i in range(1, 8)]
            previous = rows.loc[rows.local_date.isin(prior_dates)]
            if len(previous) != 7 or station.capacity is None or station.capacity <= 0:
                continue
            predicted = min(float(station.capacity), max(0., float(previous.mean_bikes.mean())))
            errors.append(predicted - float(row.mean_bikes))
            correct += availability_class(predicted, station.capacity) == availability_class(row.mean_bikes, station.capacity)
        enough_test = len(errors) >= 3
        hours = forecast_hours(base, daily, station, today, target_start, target_end, reason, cadence,
            live_base=live_base, live_daily=live_daily)
        forecasts.append({'station_id': station.station_id, 'station_name': station.name,
            'hourly_forecasts': hours,
            'low_bike_hours': [h['target_start_utc'] for h in hours if h['availability_class'] == 'low'],
            'status': 'available' if reason is None else 'insufficient_data', 'reason': reason,
            'target_date': target_date.isoformat(), 'target_start_utc': target_start.astimezone(UTC).isoformat(),
            'target_end_utc': target_end.astimezone(UTC).isoformat(),
            'input_cutoff_utc': cutoff.isoformat(), 'capacity': station.capacity,
            'qualified_days': len(live_history), 'actual_qualified_days': len(history),
            'uses_estimated_data': estimated_samples > 0,
            'input_estimated_samples': estimated_samples, 'input_actual_samples': actual_samples,
            'predicted_mean_bikes': estimate,
            'availability_class': availability_class(estimate, station.capacity) if estimate is not None else None,
            'evaluation_samples': len(errors), 'evaluation_status': 'available' if enough_test else 'insufficient_data',
            'mae': float(np.mean(np.abs(errors))) if enough_test else None,
            'rmse': float(np.sqrt(np.mean(np.square(errors)))) if enough_test else None,
            'classification_accuracy': correct / len(errors) if enough_test else None})
    return {**tables,
        'day_ahead': {'method': 'matching_hour_previous_seven_covered_days_minimum_five_hours',
            'target': 'next_local_calendar_day_hourly_mean_rentable_bikes',
            'classification_method': 'predicted_availability_ratio_thresholds_20_80_percent',
            'items': forecasts}}


def generate_pattern_plots(frame, stations, tables, cadence, cutoff, output):
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from math import ceil
    from eda.localization import WEEKDAYS

    saved = []
    if not stations or frame.empty:
        return saved
    values = statistical_values(frame)
    def facets(title):
        fig, axes = plt.subplots(ceil(len(stations) / 2), 2,
            figsize=(14, max(3.5, ceil(len(stations) / 2) * 3)), squeeze=False)
        for ax in axes.flat[len(stations):]:
            ax.axis('off')
        for ax, station in zip(axes.flat, stations):
            ax.set_title(station.name, fontsize=10)
        fig.suptitle(title, fontsize=14, color='#123b3a')
        return fig, list(axes.flat)
    def save(fig, filename, title):
        fig.tight_layout(rect=(0, 0, 1, .97))
        fig.savefig(output / filename, dpi=140, bbox_inches='tight')
        plt.close(fig)
        saved.append({'file': f'figures/{filename}', 'title': title})
    local_cutoff = pd.Timestamp(cutoff).tz_convert(ZONE)
    for name, days, caption in [('day', 1, 'ngày'), ('week', 7, 'tuần'), ('month', 30, 'tháng (30 ngày)')]:
        lower = local_cutoff - pd.DateOffset(days=days)
        for kind, label in [('line', 'Đường thời gian'), ('scatter', 'Phân tán theo thời gian'), ('histogram', 'Phân phối')]:
            title = f'{label} · Phạm vi {caption} · Chỉ dùng dữ liệu đã có'
            fig, axes = facets(title)
            for ax, station in zip(axes, stations):
                rows = frame.loc[frame.index.isin(values.index) & (frame.station_id == station.station_id)
                    & (frame.sampled_at >= lower) & (frame.sampled_at < cutoff)].sort_values('sampled_at')
                series = values.loc[rows.index, 'available_bikes']
                if not series.notna().any():
                    ax.text(.5, .5, 'Chưa có mẫu hợp lệ', ha='center', transform=ax.transAxes)
                elif kind == 'histogram':
                    ax.hist(series.dropna(), bins='sturges', color='#167c70', edgecolor='white')
                elif kind == 'scatter':
                    ax.scatter(rows.sampled_at, series, color='#167c70', s=5, alpha=.6)
                else:
                    xs, ys, previous = [], [], None
                    for at, value in zip(rows.sampled_at, series):
                        if previous is not None and not cadence.adjacent(previous, at.to_pydatetime()):
                            xs.append(at); ys.append(np.nan)
                        xs.append(at); ys.append(value)
                        previous = at.to_pydatetime()
                    ax.plot(xs, ys, color='#167c70', linewidth=1)
                if kind != 'histogram':
                    ax.set_xlim(lower, local_cutoff)
                    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=5))
                    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m\n%H:%M', tz=ZONE))
                    ax.set_xlabel('Thời điểm (New York)'); ax.set_ylabel('Số xe có thể thuê')
                else:
                    ax.set_xlabel('Số xe có thể thuê'); ax.set_ylabel('Số mẫu')
            save(fig, f'{kind}_{name}.png', title)
    # Monthly trend only with sufficient full calendar months; otherwise weekly.
    monthly = tables['monthly']
    use_month = not monthly.empty and monthly.groupby('station_id').complete.sum().min() >= 3
    period_name = 'tháng' if use_month else 'tuần'
    trend = monthly if use_month else tables['weekly']
    title = f'Xu hướng sau tổng hợp theo {period_name} · Trung bình các ngày đủ độ phủ'
    fig, axes = facets(title)
    for ax, station in zip(axes, stations):
        selected = trend.loc[trend.station_id == station.station_id] if not trend.empty else trend
        ready = selected.loc[selected.complete] if not selected.empty else selected
        if len(ready) < 2:
            ax.set_xticks([]); ax.set_yticks([])
            ax.text(.5, .5, f'Cần ít nhất 2 {period_name} trọn vẹn\nMỗi ngày đạt độ phủ từ 80%',
                ha='center', transform=ax.transAxes)
        else:
            ax.plot(range(len(selected)), selected.mean_bikes, marker='o', color='#167c70')
            ax.set_xticks(range(len(selected)), selected.period, rotation=25, fontsize=7)
        ax.set_ylabel('Số xe trung bình'); ax.set_xlabel(f'Kỳ tổng hợp theo {period_name}')
    save(fig, 'resampled_trend.png', title)
    title = 'Đường mùa vụ theo tuần · So sánh các thứ giữa những tuần trọn vẹn'
    fig, axes = facets(title)
    for ax, station in zip(axes, stations):
        weekly = tables['weekly']
        weeks = weekly.loc[(weekly.station_id == station.station_id) & weekly.complete, 'period'] if not weekly.empty else []
        daily = tables['daily']
        if len(weeks) < 2:
            ax.set_yticks([])
            ax.text(.5, .5, 'Chưa đủ 2 tuần trọn vẹn để so sánh mùa vụ\nKhông suy diễn chu kỳ từ dữ liệu ngắn',
                ha='center', transform=ax.transAxes)
        else:
            for week in weeks:
                rows = daily.loc[(daily.station_id == station.station_id) & (daily.week == week)]
                ax.plot(rows.date.dt.dayofweek, rows.mean_bikes, marker='.', label=week)
            ax.legend(fontsize=6)
        ax.set_xticks(range(7), WEEKDAYS, rotation=15, fontsize=8)
        ax.set_ylabel('Số xe trung bình ngày')
    save(fig, 'weekly_seasonality.png', title)
    return saved
