from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, StatementError

from ingestion.clients.http import SourceError
from ingestion.normalizer import normalize_station
from ingestion.clients.weather_client import WeatherClient
from ingestion.collector import collect_once
from shared.models import (BikeObservation, CollectionRun, ObservationWeatherLink, Station,
                           WeatherObservation)
from shared.time import collection_instant


def total(session, model):
    return session.scalar(select(func.count()).select_from(model))


def clients(settings, now, row, payload):
    status = {"station_id": row["station_id"], "num_bikes_available": 7, "num_docks_available": 2,
              "is_installed": 1, "is_renting": 1, "is_returning": 1,
              "last_reported": int(now.timestamp()) - 60}
    def fetch(ids):
        return [normalize_station(row, status, version="1.1", collected_at=now,
            feed_last_updated=now, information_updated_at=now, max_age=600)]
    citibike = SimpleNamespace(fetch=fetch, status=status)
    http = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    return citibike, WeatherClient(http, settings), http


def test_success_idempotency_and_utc(session, settings, now, station_row, weather_payload):
    citibike, weather, http = clients(settings, now, station_row, weather_payload)
    with http:
        run = collect_once(session, citibike, weather, settings.station_ids)
        again = collect_once(session, citibike, weather, settings.station_ids)
    assert run.status == "success" and again.id == run.id and run.attempt_count == 1
    assert total(session, BikeObservation) == total(session, WeatherObservation) == total(session, ObservationWeatherLink) == 1
    session.expire_all()
    bike = session.scalar(select(BikeObservation))
    assert bike.collected_at == now and bike.sampled_at == collection_instant(now)
    assert bike.source_observed_at == now - timedelta(seconds=60)
    assert bike.source == "citibike" and bike.available_docks == 2


def test_immediate_restart_is_not_collapsed_into_old_five_minute_slot(session, settings, now,
                                                                    station_row, weather_payload, monkeypatch):
    citibike, weather, http = clients(settings, now, station_row, weather_payload)
    with http:
        first = collect_once(session, citibike, weather, settings.station_ids)
        monkeypatch.setattr("ingestion.collector.utcnow", lambda: now + timedelta(seconds=1))
        second = collect_once(session, citibike, weather, settings.station_ids)
    assert first.id != second.id
    assert second.scheduled_at == first.scheduled_at + timedelta(seconds=1)


def test_weather_failure_keeps_bikes_and_retry_adds_link(session, settings, now, station_row, weather_payload):
    citibike, weather, http = clients(settings, now, station_row, weather_payload)

    def unavailable(*args):
        raise SourceError("open-meteo: HTTP 503")

    with http:
        run = collect_once(session, citibike, SimpleNamespace(fetch=unavailable, settings=settings), settings.station_ids)
        assert run.status == "partial" and run.success_count == 1
        assert total(session, BikeObservation) == 1 and total(session, ObservationWeatherLink) == 0
        # Bike snapshot stays immutable even if Citi Bike would now return another count.
        citibike.status["num_bikes_available"] = 99
        run = collect_once(session, citibike, weather, settings.station_ids)
    assert run.status == "success" and run.attempt_count == 2
    assert total(session, CollectionRun) == total(session, BikeObservation) == 1
    assert session.scalar(select(BikeObservation)).available_bikes == 7
    assert total(session, ObservationWeatherLink) == 1


def test_missing_bike_count_is_not_zero(session, settings, now, station_row, weather_payload):
    citibike, weather, http = clients(settings, now, station_row, weather_payload)
    citibike.status["num_bikes_available"] = None
    with http:
        run = collect_once(session, citibike, weather, settings.station_ids)
    bike = session.scalar(select(BikeObservation))
    assert run.status == "failed" and run.success_count == 0
    assert bike.available_bikes is None and bike.quality_status == "missing"


def test_missing_weather_remains_partial_on_retry(session, settings, now, station_row, weather_payload):
    weather_payload["current"]["rain"] = None
    citibike, weather, http = clients(settings, now, station_row, weather_payload)
    with http:
        collect_once(session, citibike, weather, settings.station_ids)
        run = collect_once(session, citibike, weather, settings.station_ids)
    assert run.status == "partial" and total(session, WeatherObservation) == 1
    assert session.scalar(select(WeatherObservation)).rain is None


def test_same_weather_reused_across_periods(session, settings, now, station_row, weather_payload, monkeypatch):
    citibike, weather, http = clients(settings, now, station_row, weather_payload)
    with http:
        collect_once(session, citibike, weather, settings.station_ids)
        later = now + timedelta(minutes=5)
        monkeypatch.setattr("ingestion.collector.utcnow", lambda: later)
        # Fresh source snapshot in the next sampling period.
        data = normalize_station(station_row, dict(citibike.status, last_reported=int(later.timestamp())-60),
            version="1.1", collected_at=later, feed_last_updated=later, information_updated_at=later, max_age=600)
        citibike.fetch = lambda ids: [data]
        run = collect_once(session, citibike, weather, settings.station_ids)
    assert run.status == "success"
    assert total(session, BikeObservation) == total(session, ObservationWeatherLink) == 2
    assert total(session, WeatherObservation) == 1


def test_citibike_failure_is_recorded(session, settings, now):
    def unavailable(ids):
        raise SourceError("citibike: HTTP 503")

    run = collect_once(session, SimpleNamespace(fetch=unavailable), None, settings.station_ids)
    assert run.status == "failed" and run.error_count > 0
    assert run.error_count == 1
    assert "absent or invalid" not in run.error_summary
    assert total(session, BikeObservation) == 0 and run.finished_at is not None


def test_missing_stations_are_only_reported_after_successful_feed_fetch(session, settings):
    run = collect_once(session, SimpleNamespace(fetch=lambda ids: []), None, settings.station_ids)
    assert run.status == "failed"
    assert run.error_count == len(settings.station_ids)
    assert "absent or invalid in feeds" in run.error_summary


def test_no_realtime_backfill(session, settings, now):
    with pytest.raises(ValueError, match="no historical backfill"):
        collect_once(session, None, None, settings.station_ids, scheduled_at=now - timedelta(minutes=5))
    assert total(session, CollectionRun) == 0


def test_unexpected_failure_rolls_back_publication(session, settings, now, station_row, weather_payload):
    citibike, weather, http = clients(settings, now, station_row, weather_payload)

    def crash(*args):
        raise RuntimeError("test-only interruption")

    weather.fetch = crash
    with http, pytest.raises(RuntimeError):
        collect_once(session, citibike, weather, settings.station_ids)
    assert total(session, BikeObservation) == 0
    run = session.scalar(select(CollectionRun))
    assert run.status == "failed" and run.finished_at is not None


def test_unique_constraint_and_history_protection(session, settings, now, station_row, weather_payload):
    citibike, weather, http = clients(settings, now, station_row, weather_payload)
    with http:
        run = collect_once(session, citibike, weather, settings.station_ids)
    session.add(BikeObservation(source="citibike", station_id="TEST-STATION", collection_run_id=run.id,
        sampled_at=run.scheduled_at, collected_at=now, available_bikes=1, quality_status="valid"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.delete(session.get(Station, ("citibike", "TEST-STATION")))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_naive_datetime_rejected(session, now):
    session.add(CollectionRun(scheduled_at=now.replace(tzinfo=None), started_at=now,
                              status="running", success_count=0, error_count=0, attempt_count=1))
    with pytest.raises(StatementError, match="timezone"):
        session.commit()
    session.rollback()


def test_citibike_does_not_modify_legacy_station(session, settings, now, station_row, weather_payload):
    session.add(Station(source="seoul", station_id="TEST-STATION", name="Legacy station",
                        latitude=37.5, longitude=127, rack_count=12, is_monitored=True, updated_at=now))
    session.commit()
    citibike, weather, http = clients(settings, now, station_row, weather_payload)
    with http:
        collect_once(session, citibike, weather, settings.station_ids)
    legacy = session.get(Station, ("seoul", "TEST-STATION"))
    assert legacy.name == "Legacy station" and legacy.rack_count == 12 and legacy.is_monitored
    assert legacy.capacity is None
    current = session.get(Station, ("citibike", "TEST-STATION"))
    assert current.capacity == 5 and current.rack_count is None


def test_weather_called_at_each_station_coordinates(session, settings, now, station_row, weather_payload):
    from dataclasses import replace
    citibike, weather, http = clients(settings, now, station_row, weather_payload)
    first = citibike.fetch(None)[0]
    second = replace(first, station_id="TEST-SECOND", latitude=first.latitude + 1, longitude=first.longitude + 1)
    citibike.fetch = lambda ids: [first, second]
    original = weather.fetch
    coordinates = []
    def tracked(lat, lon):
        coordinates.append((lat, lon))
        return original(lat, lon)
    weather.fetch = tracked
    with http:
        collect_once(session, citibike, weather, (first.station_id, second.station_id))
    assert coordinates == [(first.latitude, first.longitude), (second.latitude, second.longitude)]
