from datetime import timedelta

import pytest

from shared.models import BikeObservation, CollectionRun, ObservationWeatherLink, Station, WeatherObservation
from shared.repositories.silver import bike_observations, observation_weather


def insert(session, now, *, status="success", quality="valid", source="citibike", finished=True):
    session.add(Station(source=source, station_id="test-only", name="Unit test only", latitude=40.75,
                        longitude=-73.99, updated_at=now))
    run = CollectionRun(source=source, scheduled_at=now, started_at=now, status=status,
                        finished_at=now if finished else None, success_count=1, error_count=0)
    session.add(run)
    session.flush()
    bike = BikeObservation(source=source, station_id="test-only", collection_run_id=run.id,
        sampled_at=now, collected_at=now, source_observed_at=now, available_bikes=0,
        quality_status=quality, is_installed=True, is_renting=quality != "inactive")
    session.add(bike)
    session.commit()
    return bike


@pytest.mark.parametrize("status,finished,quality,expected", [
    ("success", True, "valid", 1), ("partial", True, "valid", 1),
    ("running", False, "valid", 0), ("success", False, "valid", 0),
    ("failed", True, "valid", 0), ("success", True, "inactive", 0), ("success", True, "stale", 0)])
def test_only_completed_usable_silver_is_published(session, now, status, finished, quality, expected):
    insert(session, now, status=status, finished=finished, quality=quality)
    assert len(session.scalars(bike_observations()).all()) == expected


def test_source_isolation_and_as_of_cutoff(session, now):
    insert(session, now, source="seoul")
    assert session.scalars(bike_observations()).all() == []
    assert len(session.scalars(bike_observations(source="seoul", available_at=now)).all()) == 1
    assert session.scalars(bike_observations(source="seoul", available_at=now - timedelta(seconds=1))).all() == []


def test_ui_may_read_inactive_with_explicit_policy(session, now):
    insert(session, now, quality="inactive")
    assert len(session.scalars(bike_observations(include_unusable=True)).all()) == 1


def test_weather_query_is_composable(session, now):
    insert(session, now)
    assert session.execute(observation_weather(available_at=now)).all() == []


def test_weather_not_yet_collected_is_excluded_from_features(session, now):
    bike = insert(session, now)
    weather = WeatherObservation(requested_latitude=40.75, requested_longitude=-73.99,
        weather_time=now - timedelta(minutes=5), collected_at=now + timedelta(seconds=10),
        temperature=10, humidity=60, rain=0, wind_speed=1, interval_seconds=900,
        units={"temperature_2m": "°C", "relative_humidity_2m": "%", "rain": "mm", "wind_speed_10m": "m/s"})
    session.add(weather)
    session.flush()
    session.add(ObservationWeatherLink(bike_observation_id=bike.id, weather_observation_id=weather.id))
    session.commit()
    assert session.execute(observation_weather(available_at=now)).all() == []
    assert len(session.execute(observation_weather(available_at=now + timedelta(seconds=10))).all()) == 1
