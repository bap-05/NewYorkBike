"""Load published Silver only; retain incomplete rows for quality auditing."""
import json

import numpy as np
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import aliased

from analysis.dataset import selected_stations
from analysis.statistics import usable_bike, usable_weather
from shared.models import BikeObservation, CollectionRun, ObservationWeatherLink, WeatherObservation
from shared.repositories.silver import bike_observations

NUMERIC = ['available_bikes', 'available_docks', 'temperature', 'humidity', 'rain', 'wind_speed']
WEATHER = NUMERIC[2:]
TIME_COLUMNS = ['sampled_at', 'collected_at', 'source_observed_at', 'weather_time']
BASE_COLUMNS = ['observation_id', 'source', 'station_id', 'station_name', 'capacity',
                'quality_status', 'bike_usable', 'weather_usable', 'weather_id',
                'weather_units', 'weather_interval_seconds'] + NUMERIC + TIME_COLUMNS


def published_eda_history(source, cutoff):
    """Retrospective EDA may include real archive imports; live workers keep their source contract."""
    return bike_observations(source=source,available_at=cutoff,include_unusable=True,include_archived=True)


def load_frame(session, settings, options, start, cutoff, max_rows=100000, *, include_weather=True):
    stations = selected_stations(session, settings)
    by_id = {station.station_id: station for station in stations}
    visible = published_eda_history(settings.bike_source,cutoff)
    firsts = dict(session.execute(visible.with_only_columns(BikeObservation.station_id,
        func.min(BikeObservation.sampled_at)).where(BikeObservation.station_id.in_(by_id),
        BikeObservation.sampled_at < cutoff).group_by(BikeObservation.station_id)).all())
    weather_run = aliased(CollectionRun)
    query = visible
    if include_weather:
        query = query.add_columns(WeatherObservation, weather_run.status,
            weather_run.finished_at, weather_run.source).outerjoin(ObservationWeatherLink,
            ObservationWeatherLink.bike_observation_id == BikeObservation.id).outerjoin(
            WeatherObservation, WeatherObservation.id == ObservationWeatherLink.weather_observation_id).outerjoin(
            weather_run, weather_run.id == WeatherObservation.collection_run_id)
    query = query.where(
        BikeObservation.station_id.in_(by_id), BikeObservation.sampled_at >= start,
        BikeObservation.sampled_at < cutoff).order_by(BikeObservation.sampled_at, BikeObservation.id).limit(max_rows + 1)
    records = []
    # Stream ORM batches instead of buffering every observation (and joined
    # weather object) in memory before building the analytical frame.
    with session.execute(query.execution_options(yield_per=500)) as results:
        for result in results:
            bike, weather, weather_status, weather_finished, weather_source = (
                result if include_weather else (result[0], None, None, None, None))
            if len(records) >= max_rows:
                raise ValueError('EDA row limit exceeded; narrow the requested date range')
            station = by_id[bike.station_id]
            published = weather is not None and (weather.collection_run_id is None or (
                weather_status in ('success', 'partial') and weather_finished is not None
                and weather_finished <= cutoff and weather_source == settings.bike_source))
            row = {'observation_id': bike.id, 'source': bike.source, 'station_id': bike.station_id,
                'station_name': station.name, 'capacity': station.capacity, 'quality_status': bike.quality_status,
                'sampled_at': bike.sampled_at, 'collected_at': bike.collected_at,
                'source_observed_at': bike.source_observed_at, 'available_bikes': bike.available_bikes,
                'available_docks': bike.available_docks, 'bike_usable': usable_bike(bike),
                'weather_usable': usable_weather(weather, bike, station, cutoff, options,
                    settings.weather_max_age_seconds, published),
                'weather_id': weather.id if weather else None,
                'weather_time': weather.weather_time if weather else None,
                'weather_units': json.dumps(weather.units, ensure_ascii=False) if weather else None,
                'weather_interval_seconds': weather.interval_seconds if weather else None}
            row.update({column: getattr(weather, column) if weather else None for column in WEATHER})
            records.append(row)
    frame = pd.DataFrame(records, columns=BASE_COLUMNS)
    for column in TIME_COLUMNS:
        frame[column] = pd.to_datetime(frame[column], utc=True)
    for column in NUMERIC + ['capacity']:
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    for column in ['bike_usable', 'weather_usable']:
        frame[column] = frame[column].astype(bool)
    frame['sampled_at_local'] = frame.sampled_at.dt.tz_convert(options.timezone_name)
    frame['local_date'] = frame.sampled_at_local.dt.strftime('%Y-%m-%d')
    frame['local_hour'] = frame.sampled_at_local.dt.hour
    frame['local_weekday'] = frame.sampled_at_local.dt.day_of_week
    return frame, stations, firsts


def mark_latest_slots(frame, cadence):
    frame = frame.copy()
    frame['slot_utc'] = pd.to_datetime([cadence.slot_at(value.to_pydatetime()) for value in frame.sampled_at], utc=True)
    # Current-source observations take precedence if an archive overlaps their slot,
    # including a newer inactive/invalid marker. Never replace it with an older valid archive.
    ordered = frame.assign(_archive_priority=frame.source.ne('citibike_historical').astype(int)).sort_values(
        ['_archive_priority','sampled_at', 'collected_at', 'observation_id'])
    latest = ordered.drop_duplicates(['station_id', 'slot_utc'], keep='last').index
    frame['slot_latest'] = frame.index.isin(latest)
    return frame


def statistical_values(frame):
    """Different cohorts per column: missing weather does not remove usable bikes."""
    values = frame.loc[frame.slot_latest, NUMERIC].copy()
    bikes = frame.loc[values.index, 'bike_usable']
    weather = frame.loc[values.index, 'weather_usable'] & bikes
    values.loc[~bikes, ['available_bikes', 'available_docks']] = np.nan
    values.loc[values.available_docks < 0, 'available_docks'] = np.nan
    values.loc[~weather, WEATHER] = np.nan
    return values.where(np.isfinite(values))
