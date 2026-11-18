"""Retrospective daily STL on contiguous, quality-gated real hourly observations."""
from hashlib import sha256

import numpy as np
import pandas as pd

PERIOD = 24
MIN_HOURS = 7 * PERIOD
MIN_COVERAGE = .8
COMPONENT_COLUMNS = ['station_id', 'hour_utc', 'observed', 'trend', 'seasonal', 'residual']


def image_name(station_id):
    token = sha256(station_id.encode()).hexdigest()[:16].translate(str.maketrans('0123456789', 'ghijklmnop'))
    return f'decomposition_{token}.png'


def decompose(frame, stations, cadence, start, cutoff, timezone='America/New_York'):
    """No imputation: every selected hour must independently meet cadence coverage.

    Split at missing hours and DST offset changes so a 24-step cycle stays aligned
    with the local clock. Select the most recent qualifying segment, not today's
    possibly incomplete tail. This retrospective smoother is never a forecast input.
    """
    from statsmodels.tsa.seasonal import STL

    lower, upper = pd.Timestamp(start).ceil('h'), pd.Timestamp(cutoff).floor('h')
    expected = {}
    if lower < upper:
        for tick in cadence.slots(lower.to_pydatetime(), upper.to_pydatetime()):
            hour = pd.Timestamp(tick).floor('h')
            expected[hour] = expected.get(hour, 0) + 1
    hourly_index = pd.date_range(lower, upper, freq='h', inclusive='left') if lower < upper else pd.DatetimeIndex([], tz='UTC')
    real = frame.loc[frame.slot_latest & frame.bike_usable
        & ~frame.source.str.endswith('_estimated') & frame.available_bikes.notna()].copy()
    real['hour_utc'] = real.sampled_at.dt.floor('h')
    real = real.loc[real.hour_utc.isin(hourly_index)]
    results, components = [], []
    for station in stations:
        rows = real.loc[real.station_id == station.station_id]
        grouped = rows.groupby('hour_utc').available_bikes.agg(['mean', 'count'])
        coverage = grouped['count'].div(pd.Series(expected, dtype=float)).reindex(hourly_index).fillna(0.)
        series = grouped['mean'].reindex(hourly_index).where(coverage >= MIN_COVERAGE)
        segments, current, previous_offset = [], [], None
        for at, value in series.items():
            offset = at.tz_convert(timezone).utcoffset()
            if pd.isna(value) or (current and offset != previous_offset):
                if current:
                    segments.append(current)
                current = []
            if pd.notna(value):
                current.append((at, float(value)))
            previous_offset = offset
        if current:
            segments.append(current)
        candidates = [segment for segment in segments if len(segment) >= MIN_HOURS]
        item = dict(station_id=station.station_id, station_name=station.name,
            status='insufficient_data', reason='requires_seven_contiguous_covered_days',
            period_hours=PERIOD, minimum_hours=MIN_HOURS, minimum_hourly_coverage=MIN_COVERAGE,
            qualified_hours=int(series.notna().sum()),
            longest_segment_hours=max(map(len, segments), default=0), selected_hours=0,
            start_utc=None, end_utc=None, minimum_selected_coverage=None,
            method='STL', robust=True, imputed_hours=0, retrospective_only=True)
        if candidates:
            chosen = max(candidates, key=lambda segment: segment[-1][0])
            index = pd.DatetimeIndex([at for at, _ in chosen])
            observed = pd.Series([value for _, value in chosen], index=index)
            fit = STL(observed.to_numpy(), period=PERIOD, robust=True).fit()
            data = pd.DataFrame(dict(station_id=station.station_id, hour_utc=index,
                observed=observed.to_numpy(), trend=fit.trend, seasonal=fit.seasonal, residual=fit.resid))
            assert np.isfinite(data[['observed', 'trend', 'seasonal', 'residual']].to_numpy()).all()
            components.append(data)
            item.update(status='available', reason=None, selected_hours=len(chosen),
                start_utc=index[0].isoformat(), end_utc=(index[-1]+pd.Timedelta(hours=1)).isoformat(),
                minimum_selected_coverage=float(coverage.loc[index].min()))
        results.append(item)
    return results, pd.concat(components, ignore_index=True) if components else pd.DataFrame(columns=COMPONENT_COLUMNS)


def generate_decomposition_plots(results, components, output, timezone='America/New_York'):
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from zoneinfo import ZoneInfo

    output.mkdir(parents=True, exist_ok=True)
    figures = []
    zone = ZoneInfo(timezone)
    for item in results:
        fig, axes = plt.subplots(4, 1, figsize=(12, 9), sharex=True, constrained_layout=True)
        title = f'Phân rã chuỗi thời gian · {item["station_name"]}'
        fig.suptitle(title, fontsize=15, color='#123b3a')
        labels = [('observed', 'Chuỗi gốc', '#167c70'), ('trend', 'Xu hướng', '#3f6fb0'),
            ('seasonal', 'Mùa vụ · chu kỳ 24 giờ', '#8a63b8'), ('residual', 'Phần dư', '#ad6638')]
        if item['status'] == 'available':
            data = components.loc[components.station_id == item['station_id']]
            for ax, (column, label, color) in zip(axes, labels):
                ax.plot(data.hour_utc, data[column], color=color, linewidth=1.2)
                ax.set_ylabel(f'{label}\n(xe)')
                ax.grid(alpha=.2)
                if column in ('seasonal', 'residual'):
                    ax.axhline(0, color='#869390', linewidth=.6)
            first, last = (pd.Timestamp(item[key]).tz_convert(zone) for key in ('start_utc', 'end_utc'))
            axes[0].set_title(f'{first:%d/%m/%Y %H:%M %Z} → {last:%d/%m/%Y %H:%M %Z}', fontsize=10)
            locator = mdates.AutoDateLocator(minticks=4, maxticks=7, tz=zone)
            axes[-1].xaxis.set_major_locator(locator)
            axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%d/%m\n%H:%M %Z', tz=zone))
            axes[-1].set_xlabel('Giờ New York')
        else:
            for ax, (_, label, _) in zip(axes, labels):
                ax.set_ylabel(label)
                ax.set_xticks([]); ax.set_yticks([])
            axes[1].text(.5, .5, 'Chưa đủ 7 ngày liên tục đạt độ phủ theo giờ từ 80%',
                ha='center', va='center', transform=axes[1].transAxes)
        name = image_name(item['station_id'])
        fig.savefig(output / name, dpi=140)
        plt.close(fig)
        figures.append({'file':f'figures/{name}', 'title':title, 'station_id':item['station_id']})
    return figures
