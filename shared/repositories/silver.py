"""Read contracts for future API/Gold services; never publish an unfinished run."""
from sqlalchemy import or_, select

from shared.models import BikeObservation, CollectionRun, ObservationWeatherLink, WeatherObservation
from shared.time import as_utc


def bike_observations(*, source="citibike", available_at=None, include_unusable=False):
    """Return a composable SELECT. Gold keeps the default valid-only policy."""
    query = select(BikeObservation).join(CollectionRun, CollectionRun.id == BikeObservation.collection_run_id).where(
        BikeObservation.source == source,
        CollectionRun.status.in_(("success", "partial")), CollectionRun.finished_at.is_not(None))
    if not include_unusable:
        query = query.where(BikeObservation.quality_status == "valid", BikeObservation.available_bikes.is_not(None),
                            BikeObservation.is_renting.is_not(False), BikeObservation.is_installed.is_not(False))
    if available_at is not None:
        instant = as_utc(available_at)
        query = query.where(CollectionRun.finished_at <= instant, BikeObservation.collected_at <= instant,
                            or_(BikeObservation.source_observed_at.is_(None), BikeObservation.source_observed_at <= instant))
    return query


def observation_weather(*, source="citibike", available_at=None):
    """Pairs usable for weather features. Missing units/values remain the caller's concern."""
    query = bike_observations(source=source, available_at=available_at).add_columns(WeatherObservation).join(
        ObservationWeatherLink, ObservationWeatherLink.bike_observation_id == BikeObservation.id).join(
        WeatherObservation, WeatherObservation.id == ObservationWeatherLink.weather_observation_id).where(
        WeatherObservation.weather_time <= BikeObservation.collected_at)
    if available_at is not None:
        instant = as_utc(available_at)
        query = query.where(WeatherObservation.weather_time <= instant, WeatherObservation.collected_at <= instant)
    return query
