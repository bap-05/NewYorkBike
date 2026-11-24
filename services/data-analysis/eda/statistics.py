"""Descriptive statistics, review flags, schedule-aware coverage and train-only scaling."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from eda.dataset import NUMERIC, WEATHER, statistical_values
from shared.time import UTC


def descriptive_statistics(frame):
    values = statistical_values(frame)
    result = []
    groups = [('ALL', values.index)] + [(str(key), group.index) for key, group in
        frame.loc[values.index].groupby('station_id', sort=True)]
    for station_id, indices in groups:
        for column in NUMERIC:
            series = values.loc[indices, column].dropna()
            modes = series.mode()
            result.append({'station_id': station_id, 'column': column,
                'count': int(series.count()), 'missing_or_unusable': int(len(indices) - series.count()),
                'mean': series.mean(), 'median': series.median(),
                'std_population': series.std(ddof=0), 'std_sample': series.std(ddof=1),
                'min': series.min(), 'q1': series.quantile(.25), 'q3': series.quantile(.75),
                'max': series.max(), 'mode_values': modes.head(20).tolist(),
                'mode_count': len(modes), 'modes_truncated': len(modes) > 20,
                'mode_frequency': int(series.value_counts().max()) if len(series) else None})
    return pd.DataFrame(result)


def missingness(frame, stations):
    values = statistical_values(frame)
    result = []
    for station in stations:
        raw = frame.loc[frame.station_id == station.station_id]
        rows = raw.loc[raw.slot_latest]
        result.append({'station_id': station.station_id, 'station_name': station.name,
            'raw_rows': len(raw), 'deduplicated_rows': len(rows), 'duplicate_slot_rows': len(raw) - len(rows),
            'usable_bike_rows': int(rows.bike_usable.sum()),
            'inactive_rows': int((rows.quality_status == 'inactive').sum()),
            'unusable_bike_rows': int((~rows.bike_usable).sum()),
            'missing_weather_link_rows': int(rows.weather_id.isna().sum()),
            'weather_unusable_rows': int((~rows.weather_usable).sum()),
            'usable_bikes_without_usable_weather': int((rows.bike_usable & ~rows.weather_usable).sum()),
            'distinct_weather_observations': int(rows.weather_id.nunique()),
            **{f'{column}_missing_raw': int(rows[column].isna().sum()) for column in NUMERIC},
            **{f'{column}_unusable_pct': (100 * values.loc[rows.index, column].isna().mean()) if len(rows) else None
               for column in NUMERIC}})
    return pd.DataFrame(result)


def daily_coverage(frame, stations, firsts, cadence, options, start, cutoff):
    zone = ZoneInfo(options.timezone_name)
    result = []
    # Partition once instead of scanning the full multi-station frame per day.
    groups = frame.loc[frame.slot_latest].groupby(['station_id', 'local_date']).groups
    empty = frame.iloc[:0]
    for station in stations:
        first = firsts.get(station.station_id)
        day = start.astimezone(zone).date()
        while datetime.combine(day, time.min, zone).astimezone(UTC) < cutoff:
            begin = max(start, datetime.combine(day, time.min, zone).astimezone(UTC))
            end = min(cutoff, datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(UTC))
            indices = groups.get((station.station_id, day.isoformat()))
            rows = frame.loc[indices] if indices is not None else empty
            rows = rows.loc[(rows.sampled_at >= begin) & (rows.sampled_at < end)]
            expected = set()
            if first is not None:
                lower = max(begin, cadence.slot_at(first))
                due_end = min(end, cutoff - timedelta(seconds=options.ingestion_grace_seconds) + timedelta(microseconds=1))
                expected = set(cadence.slots(lower, due_end))
                expected.update(row.to_pydatetime() for row in rows.slot_utc)
            observed = len(rows)
            usable = int(rows.bike_usable.sum())
            occupied = set(row.to_pydatetime() for row in rows.slot_utc)
            result.append({'station_id': station.station_id, 'station_name': station.name,
                'local_date': day.isoformat(), 'window_start_utc': begin.isoformat(),
                'window_end_utc': end.isoformat(), 'partial_day': begin != datetime.combine(day, time.min, zone).astimezone(UTC)
                    or end != datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(UTC),
                'expected_slots': len(expected), 'observed_slots': observed, 'usable_slots': usable,
                'missing_slots': len(expected - occupied),
                'coverage': usable / len(expected) if expected else None,
                'quality_status': ('no_history' if not expected else
                    'ok' if usable / len(expected) >= options.min_coverage else 'low_coverage')})
            day += timedelta(days=1)
    return pd.DataFrame(result)


def outlier_flags(frame, cadence):
    """Review-only flags. IQR fits the EDA window, not a production preprocessing step."""
    values = statistical_values(frame)
    flags = []
    def add(index, column, reason, value, lower=None, upper=None):
        row = frame.loc[index]
        flags.append({'observation_id': int(row.observation_id), 'station_id': row.station_id,
            'station_name': row.station_name, 'sampled_at': row.sampled_at.isoformat(),
            'sampled_at_local': row.sampled_at_local.isoformat(), 'column': column,
            'reason': reason, 'value': value, 'lower_bound': lower, 'upper_bound': upper,
            'action': 'review_only_not_deleted'})
    for station_id, rows in frame.loc[frame.slot_latest].groupby('station_id'):
        rows = rows.sort_values('sampled_at')
        for column in NUMERIC:
            series = values.loc[rows.index, column].dropna()
            if len(series) >= 8:
                q1, q3 = series.quantile([.25, .75])
                width = q3 - q1
                lower, upper = q1 - 1.5 * width, q3 + 1.5 * width
                for index, value in series.loc[(series < lower) | (series > upper)].items():
                    add(index, column, 'iqr_1_5' if width else 'zero_iqr_deviation', value, lower, upper)
        previous = None
        for index, row in rows.iterrows():
            if pd.notna(row.capacity) and row.capacity > 0 and pd.notna(row.available_bikes) and row.available_bikes > row.capacity:
                add(index, 'available_bikes', 'exceeds_current_capacity_snapshot', row.available_bikes, 0, row.capacity)
            for column in ['available_bikes', 'available_docks']:
                if pd.notna(row[column]) and row[column] < 0:
                    add(index, column, 'negative_count', row[column], 0)
            if not row.bike_usable:
                previous = None
                continue
            if previous is not None and cadence.adjacent(previous.sampled_at.to_pydatetime(), row.sampled_at.to_pydatetime()):
                threshold = max(10, .5 * row.capacity) if pd.notna(row.capacity) and row.capacity > 0 else 10
                delta = abs(row.available_bikes - previous.available_bikes)
                if delta > threshold:
                    add(index, 'available_bikes', 'large_adjacent_change', delta, 0, threshold)
            previous = row
    columns = ['observation_id', 'station_id', 'station_name', 'sampled_at', 'sampled_at_local',
               'column', 'reason', 'value', 'lower_bound', 'upper_bound', 'action']
    return pd.DataFrame(flags, columns=columns)


def correlation_tables(frame):
    values = statistical_values(frame)
    result = {}
    groups = [('ALL', values.index)] + [(str(key), rows.index) for key, rows in
        frame.loc[values.index].groupby('station_id', sort=True)]
    for key, indices in groups:
        subset = values.loc[indices]
        finite = subset.notna().astype('int64')
        result[key] = {'correlation': subset.corr(min_periods=3), 'pair_counts': finite.T @ finite}
    return result


def temporal_profiles(frame):
    values = statistical_values(frame)
    rows = frame.loc[values.index, ['station_id', 'station_name', 'local_date', 'local_hour', 'local_weekday']].copy()
    rows['available_bikes'] = values.available_bikes
    result = {}
    for kind, column in [('hour', 'local_hour'), ('weekday', 'local_weekday'), ('day', 'local_date')]:
        result[kind] = rows.groupby(['station_id', 'station_name', column], dropna=False).available_bikes.agg(
            ['count', 'mean', 'median', 'std']).reset_index()
    return result


def scaling_comparison(frame):
    """Demonstrate both scalers without fitting on future rows or creating an ML model."""
    from sklearn.preprocessing import MinMaxScaler, StandardScaler
    values = statistical_values(frame)
    rows = frame.loc[values.index].sort_values(['sampled_at', 'station_id'])
    times = sorted(rows.sampled_at.unique())
    columns = ['observation_id', 'station_id', 'sampled_at', 'partition'] + [
        f'{column}_{suffix}' for column in NUMERIC for suffix in ['raw', 'minmax', 'zscore']]
    if len(times) < 10:
        return pd.DataFrame(columns=columns), {'status': 'insufficient_data', 'reason': 'fewer_than_10_distinct_timestamps'}
    validation_start, test_start = times[int(len(times) * .7)], times[int(len(times) * .85)]
    train = (rows.sampled_at < validation_start) & (rows.sampled_at + pd.Timedelta(minutes=30) < validation_start)
    validation = (rows.sampled_at >= validation_start) & (rows.sampled_at < test_start)
    validation &= rows.sampled_at + pd.Timedelta(minutes=30) < test_start
    test = rows.sampled_at >= test_start
    result = rows[['observation_id', 'station_id', 'sampled_at']].copy()
    result['partition'] = np.select([train, validation, test], ['train', 'validation', 'test'], default='purged_boundary')
    parameters = {}
    for column in NUMERIC:
        series = values.loc[rows.index, column]
        result[f'{column}_raw'] = series
        result[f'{column}_minmax'] = np.nan
        result[f'{column}_zscore'] = np.nan
        fitted = series.loc[train & series.notna()]
        if len(fitted) < 2:
            parameters[column] = {'status': 'insufficient_training_values', 'training_count': len(fitted)}
            continue
        minmax, zscore = MinMaxScaler(), StandardScaler()
        matrix = fitted.to_numpy().reshape(-1, 1)
        minmax.fit(matrix)
        zscore.fit(matrix)
        eligible = series.notna() & (result.partition != 'purged_boundary')
        matrix = series.loc[eligible].to_numpy().reshape(-1, 1)
        result.loc[eligible, f'{column}_minmax'] = minmax.transform(matrix).ravel()
        result.loc[eligible, f'{column}_zscore'] = zscore.transform(matrix).ravel()
        parameters[column] = {'training_count': len(fitted), 'min': float(minmax.data_min_[0]),
            'max': float(minmax.data_max_[0]), 'mean': float(zscore.mean_[0]), 'scale': float(zscore.scale_[0])}
    return result[columns], {'status': 'demonstration_only', 'model_trained': False,
        'validation_start_utc': pd.Timestamp(validation_start).isoformat(),
        'test_start_utc': pd.Timestamp(test_start).isoformat(),
        'partition_counts': result.partition.value_counts().to_dict(), 'parameters': parameters,
        'note': 'Fit each feature on finite training values only; keep missing values; no imputation or model activation.'}
