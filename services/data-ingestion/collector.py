"""One sampling period. No scheduler, training, analysis or prediction side effects."""
from sqlalchemy import func, select
from datetime import timedelta

from ingestion.clients.http import SourceError
from ingestion.bronze import BronzeError
from shared.models import (BikeObservation, CollectionRun, ObservationWeatherLink,
                           Station, WeatherObservation)
from shared.time import as_utc, collection_instant, utcnow


def _weather(session, values, run_id):
    observation = session.scalar(select(WeatherObservation).where(
        WeatherObservation.requested_latitude == values["requested_latitude"],
        WeatherObservation.requested_longitude == values["requested_longitude"],
        WeatherObservation.weather_time == values["weather_time"],
        WeatherObservation.source == values["source"]))
    if observation is None:
        units = values["units"]
        observation = WeatherObservation(**values, collection_run_id=run_id,
            temperature_unit=units["temperature_2m"], humidity_unit=units["relative_humidity_2m"],
            rain_unit=units["rain"], wind_speed_unit=units["wind_speed_10m"])
        session.add(observation)
        session.flush()
    # Repeated source timestamp is immutable: do not count rain repeatedly or rewrite history.
    return observation


def collect_once(session, citibike, weather, station_ids, *, scheduled_at=None, bronze=None):
    if not station_ids:
        raise ValueError("Fill STATION_IDS using real IDs from --list-stations")
    now = utcnow()
    slot = collection_instant(scheduled_at or now)
    age = (as_utc(now) - slot).total_seconds()
    if age < 0 or age >= 300:
        raise ValueError("Realtime collection requires a current timestamp; no historical backfill or future samples")
    source = "citibike"
    run = session.scalar(select(CollectionRun).where(CollectionRun.scheduled_at == slot, CollectionRun.source == source))
    if run is not None and run.status == "success":
        return run
    if run is None:
        run = CollectionRun(scheduled_at=slot, started_at=now, status="running", success_count=0,
                            error_count=0, attempt_count=1, source=source)
        session.add(run)
    else:
        run.status, run.finished_at = "running", None
        run.attempt_count += 1
    session.commit()  # Durable running marker. All following writes publish atomically with final status.
    run_id = run.id
    errors = []
    cache = {}
    bronze_path = None
    try:
        if bronze is not None:
            bronze_path = bronze.begin(run_id=run.id, attempt_count=run.attempt_count,
                                       scheduled_at=slot, source=source, station_ids=station_ids)
            run.bronze_manifest_path = bronze_path
        # Configuration is authoritative for station tracking in this first implementation.
        for station in session.scalars(select(Station).where(Station.source == source)):
            station.is_monitored = station.station_id in station_ids
        existing = {item.station_id: item for item in session.scalars(
            select(BikeObservation).where(BikeObservation.collection_run_id == run_id, BikeObservation.source == source))}
        needed = set(station_ids) - existing.keys()
        rows = []
        feed_loaded = False
        if needed:
            try:
                rows = citibike.fetch(needed)
                feed_loaded = True
                run.feed_metadata = getattr(citibike, "feed_metadata", None)
            except SourceError as exc:
                errors.append(str(exc))
        found = set()
        for data in rows:
            station_id = data.station_id
            if station_id not in needed or station_id in found:
                continue
            found.add(station_id)
            station = session.get(Station, (source, data.station_id))
            if station is None:
                station = Station(source=source, station_id=data.station_id)
                session.add(station)
            station.name, station.latitude, station.longitude = data.name, data.latitude, data.longitude
            station.capacity, station.is_monitored = data.capacity, True
            station.updated_at = data.collected_at
            station.information_updated_at = data.information_updated_at
            session.flush()
            bike = BikeObservation(source=source, station_id=data.station_id, collection_run_id=run.id,
                                   sampled_at=slot, collected_at=data.collected_at,
                                   source_observed_at=data.source_observed_at, available_bikes=data.available_bikes,
                                   available_docks=data.available_docks, is_installed=data.is_installed,
                                   is_renting=data.is_renting, is_returning=data.is_returning,
                                   feed_last_updated=data.feed_last_updated, gbfs_version=data.gbfs_version,
                                   quality_status=data.quality_status)
            session.add(bike)
            session.flush()
            existing[data.station_id] = bike
        # An unavailable feed cannot prove a station is absent. Report the
        # source failure once; only check membership after a successful fetch.
        if feed_loaded:
            for station_id in sorted(needed - found):
                errors.append(f"citibike: configured station {station_id} absent or invalid in feeds")

        for station_id, bike in existing.items():
            if bike.quality_status != "valid":
                errors.append(f"citibike: {bike.quality_status} observation for {station_id}")
            link = session.get(ObservationWeatherLink, bike.id)
            if link is not None:
                linked_weather = session.get(WeatherObservation, link.weather_observation_id)
                if bronze is not None:
                    bronze.record_weather_reuse(station_id=station_id, weather_observation_id=linked_weather.id,
                        original_run_id=linked_weather.collection_run_id, reason="existing_observation_link")
                if any(getattr(linked_weather, key) is None for key in ("temperature", "humidity", "rain", "wind_speed")):
                    errors.append(f"open-meteo: missing or invalid weather values; station {station_id}")
                continue
            station = session.get(Station, (source, station_id))
            coords = (station.latitude, station.longitude)
            cached = session.scalar(select(WeatherObservation).where(
                WeatherObservation.requested_latitude == coords[0],
                WeatherObservation.requested_longitude == coords[1],
                WeatherObservation.source == "open-meteo",
                WeatherObservation.weather_time <= bike.collected_at,
                WeatherObservation.collected_at <= bike.collected_at,
                WeatherObservation.weather_time > bike.collected_at - timedelta(seconds=min(900, weather.settings.weather_max_age_seconds)),
                WeatherObservation.temperature.is_not(None), WeatherObservation.humidity.is_not(None),
                WeatherObservation.rain.is_not(None), WeatherObservation.wind_speed.is_not(None)
            ).order_by(WeatherObservation.weather_time.desc()).limit(1))
            if cached is not None:
                session.add(ObservationWeatherLink(bike_observation_id=bike.id, weather_observation_id=cached.id))
                if bronze is not None:
                    bronze.record_weather_reuse(station_id=station_id, weather_observation_id=cached.id,
                        original_run_id=cached.collection_run_id, reason="fresh_silver_weather")
                continue
            if coords not in cache:
                try:
                    cache[coords] = weather.fetch(*coords)
                except SourceError as exc:
                    cache[coords] = exc
            values = cache[coords]
            if isinstance(values, SourceError):
                errors.append(f"{values}; station {station_id}")
                continue
            age = (bike.collected_at - values["weather_time"]).total_seconds()
            if age < 0 or age > weather.settings.weather_max_age_seconds:
                errors.append(f"open-meteo: no suitable weather at bike observation time; station {station_id}")
                continue
            observation = _weather(session, values, run_id)
            session.add(ObservationWeatherLink(bike_observation_id=bike.id, weather_observation_id=observation.id))
            if any(getattr(observation, key) is None for key in ("temperature", "humidity", "rain", "wind_speed")):
                errors.append(f"open-meteo: missing or invalid weather values; station {station_id}")

        session.flush()
        run.success_count = session.scalar(select(func.count()).select_from(BikeObservation).where(
            BikeObservation.collection_run_id == run_id, BikeObservation.quality_status == "valid"))
        run.error_count = len(errors)
        run.error_summary = "\n".join(errors) if errors else None
        run.status = "success" if not errors else ("partial" if run.success_count else "failed")
        run.finished_at = utcnow()
        if bronze is not None:
            # Archive is durable before Silver publication. This is a planned outcome,
            # not a claim that the independent MySQL commit has succeeded.
            bronze.finish("complete", planned_silver_status=run.status)
        session.commit()
        return run
    except Exception:
        session.rollback()
        if bronze is not None and bronze.active:
            try:
                bronze.finish("aborted", planned_silver_status="failed")
            except BronzeError:
                pass
        # Failed DB writes do not expose half a period. A hard crash leaves 'running'; retry can recover.
        run = session.get(CollectionRun, run_id)
        run.status, run.finished_at = "failed", utcnow()
        run.error_count = 1
        run.error_summary = "ingestion: unexpected failure; uncommitted observation writes rolled back"
        if bronze_path is not None:
            run.bronze_manifest_path = bronze_path
        session.commit()
        raise
    finally:
        if bronze is not None:
            bronze.reset()
