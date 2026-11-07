"""Read completed Silver and calculate statistics, without writing any tables."""
from collections import Counter, defaultdict
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from analysis.statistics import analysis_start, period_start, summarize, windows
from shared.models import BikeObservation, CollectionRun, ObservationWeatherLink, Station, WeatherObservation
from shared.repositories.silver import bike_observations
from shared.time import UTC


def selected_stations(session, settings):
    query = select(Station).where(Station.source == settings.bike_source)
    if settings.station_ids:
        query = query.where(Station.station_id.in_(settings.station_ids))
    else:
        query = query.where(Station.is_monitored.is_(True))
    return list(session.scalars(query.order_by(Station.station_id)))


def calculate_results(session, settings, options, cutoff, stations=None):
    stations = selected_stations(session, settings) if stations is None else stations
    ids = [s.station_id for s in stations]
    start = analysis_start(cutoff, options)
    visible = bike_observations(source=settings.bike_source, available_at=cutoff, include_unusable=True)
    firsts = dict(session.execute(visible.with_only_columns(
        BikeObservation.station_id, func.min(BikeObservation.sampled_at)).where(
        BikeObservation.station_id.in_(ids), BikeObservation.sampled_at < cutoff).group_by(BikeObservation.station_id)).all())
    weather_run = aliased(CollectionRun)
    pairs = session.execute(visible.add_columns(WeatherObservation, CollectionRun.finished_at,
            weather_run.status, weather_run.finished_at, weather_run.source)
        .outerjoin(ObservationWeatherLink, ObservationWeatherLink.bike_observation_id == BikeObservation.id)
        .outerjoin(WeatherObservation, WeatherObservation.id == ObservationWeatherLink.weather_observation_id)
        .outerjoin(weather_run, weather_run.id == WeatherObservation.collection_run_id)
        .where(BikeObservation.station_id.in_(ids), BikeObservation.sampled_at >= start,
               BikeObservation.sampled_at < cutoff)
        .order_by(BikeObservation.sampled_at, BikeObservation.id)).all()
    groups = defaultdict(list)
    zone = ZoneInfo(options.timezone_name)
    for bike, weather, finished, weather_status, weather_finished, weather_source in pairs:
        published = weather is not None and (weather.collection_run_id is None or (
            weather_status in ("success", "partial") and weather_finished is not None
            and weather_finished <= cutoff and weather_source == settings.bike_source))
        entry = (bike, weather, finished, published)
        hour = period_start(bike.sampled_at, 3600)
        day = datetime.combine(bike.sampled_at.astimezone(zone).date(), time.min, zone).astimezone(UTC)
        groups[(bike.station_id, "hour", hour)].append(entry)
        groups[(bike.station_id, "day", day)].append(entry)
    generated = []
    all_windows = windows(cutoff, options)
    for station in stations:
        first = firsts.get(station.station_id)
        if first is None:
            continue
        for aggregation, begin, end in all_windows:
            if end <= period_start(first, options.expected_interval_seconds):
                continue
            generated.extend(summarize(groups[(station.station_id, aggregation, begin)], station=station,
                first_observation=first, aggregation=aggregation, start=begin, end=end,
                cutoff=cutoff, options=options, weather_max_age=settings.weather_max_age_seconds))
    requested = set(settings.station_ids or ids)
    return generated, {"input_rows": len(pairs), "station_count": len(stations),
        "generated_metrics": len(generated), "quality_counts": dict(Counter(row["quality_status"] for row in generated)),
        "missing_metadata_station_ids": sorted(requested - set(ids)),
        "stations_without_published_history": sorted(set(ids) - set(firsts)),
        "window_start_utc": start.isoformat(), "input_cutoff_utc": cutoff.isoformat(),
        "input_watermark": max((row[2] for row in pairs), default=None)}
