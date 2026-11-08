"""One timestamp/provenance policy for training, inference and evaluation."""
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import timedelta
import math
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import aliased

from shared.models import BikeObservation, CollectionRun, ObservationWeatherLink, Station, WeatherObservation
from shared.repositories.silver import bike_observations


def stations_for(session, settings):
    query = select(Station).where(Station.source == settings.bike_source)
    query = query.where(Station.station_id.in_(settings.station_ids)) if settings.station_ids else query.where(Station.is_monitored.is_(True))
    return list(session.scalars(query.order_by(Station.station_id)))


def load_history(session, settings, cutoff, options):
    stations = stations_for(session, settings)
    ids = [s.station_id for s in stations]
    weather_run = aliased(CollectionRun)
    query = bike_observations(source=settings.bike_source, available_at=cutoff, include_unusable=True)
    rows = session.execute(query.add_columns(CollectionRun.finished_at, WeatherObservation,
            weather_run.status, weather_run.finished_at, weather_run.source)
        .outerjoin(ObservationWeatherLink, ObservationWeatherLink.bike_observation_id == BikeObservation.id)
        .outerjoin(WeatherObservation, WeatherObservation.id == ObservationWeatherLink.weather_observation_id)
        .outerjoin(weather_run, weather_run.id == WeatherObservation.collection_run_id)
        .where(BikeObservation.station_id.in_(ids), BikeObservation.sampled_at >= cutoff-timedelta(days=options.history_days),
               BikeObservation.sampled_at <= cutoff)
        .order_by(BikeObservation.sampled_at, BikeObservation.collected_at, BikeObservation.id)).all()
    groups = defaultdict(list)
    for bike, finished, weather, wstatus, wfinished, wsource in rows:
        groups[bike.station_id].append({"bike": bike, "available_at": max(finished, bike.collected_at),
            "weather": weather, "weather_published": weather is not None and (
                weather.collection_run_id is None or (wstatus in ("success","partial") and wfinished is not None
                    and wfinished <= finished and wsource == settings.bike_source))})
    return stations, groups


def usable(entry, options):
    b = entry["bike"]
    return (b.quality_status == "valid" and b.is_installed is True and b.is_renting is True
        and b.available_bikes is not None and b.available_bikes >= 0
        and b.source_observed_at is not None
        and 0 <= (b.collected_at-b.source_observed_at).total_seconds() <= options.max_bike_age_seconds
        and 0 <= (b.collected_at-b.sampled_at).total_seconds() <= options.max_bike_age_seconds)


def nearest(entries, target, tolerance):
    """Match actual timestamps, never row offsets or a synthesized missing slot."""
    if not entries:
        return None
    times = [entry["bike"].sampled_at for entry in entries]
    position = bisect_left(times, target)
    candidates = entries[max(0,position-1):position+2]
    matched = min(candidates, key=lambda e: (abs((e["bike"].sampled_at-target).total_seconds()),
        -e["bike"].collected_at.timestamp(), -e["bike"].id))
    return matched if abs((matched["bike"].sampled_at-target).total_seconds()) <= tolerance else None


def weather_values(entry, cutoff, station, settings):
    w = entry["weather"]
    if w is None or not entry["weather_published"] or w.source != "open-meteo":
        return None
    values = {"temperature":w.temperature, "humidity":w.humidity, "rain":w.rain, "wind_speed":w.wind_speed}
    if any(v is None or not math.isfinite(v) for v in values.values()):
        return None
    units = {"temperature_2m":"\u00b0C", "relative_humidity_2m":"%", "rain":"mm", "wind_speed_10m":"m/s"}
    if (any((w.units or {}).get(k) != v for k,v in units.items()) or w.collected_at > cutoff
            or not 0 <= (cutoff-w.weather_time).total_seconds() <= settings.weather_max_age_seconds
            or w.interval_seconds <= 0 or w.requested_latitude != station.latitude
            or w.requested_longitude != station.longitude or not 0 <= w.humidity <= 100
            or w.rain < 0 or w.wind_speed < 0):
        return None
    return values


def feature_values(entry, history, station, settings, options):
    b, cutoff = entry["bike"], entry["available_at"]
    earlier = [e for e in history if e["bike"].sampled_at < b.sampled_at and e["available_at"] <= cutoff]
    lag = nearest(earlier, b.sampled_at-timedelta(minutes=30), options.timestamp_tolerance_seconds)
    if lag is None or not usable(lag,options):
        return None
    local = b.sampled_at.astimezone(ZoneInfo("America/New_York"))
    hour = local.hour+local.minute/60
    values = {"station_id":station.station_id, "bikes_now":float(b.available_bikes),
        "bikes_lag30":float(lag["bike"].available_bikes),
        "change30":float(b.available_bikes-lag["bike"].available_bikes),
        "hour_sin":math.sin(2*math.pi*hour/24), "hour_cos":math.cos(2*math.pi*hour/24),
        "weekday_sin":math.sin(2*math.pi*local.weekday()/7), "weekday_cos":math.cos(2*math.pi*local.weekday()/7),
        "is_weekend":int(local.weekday()>=5)}
    return {"base":values, "weather":weather_values(entry,cutoff,station,settings),
        "lag_observation_id":lag["bike"].id, "weather_observation_id":entry["weather"].id if entry["weather"] else None}


def training_examples(stations, groups, settings, options):
    result, excluded = [], Counter()
    for station in stations:
        history = groups[station.station_id]
        # Keep real observation identities and timestamps; never synthesize missing slots.
        for entry in history:
            b = entry["bike"]
            if not usable(entry,options):
                excluded["unusable_input"] += 1
                continue
            target = b.sampled_at+timedelta(seconds=options.horizon_seconds)
            label = nearest(history,target,options.timestamp_tolerance_seconds)
            if label is None or not usable(label,options) or label["bike"].source_observed_at <= b.source_observed_at:
                excluded["missing_or_unusable_target"] += 1
                continue
            if label["bike"].sampled_at <= entry["available_at"] or target <= entry["available_at"]:
                excluded["target_not_in_future_at_issue"] += 1
                continue
            features = feature_values(entry,history,station,settings,options)
            result.append({"station_id":station.station_id,"input_observation_id":b.id,
                "input_time":b.sampled_at,"feature_cutoff":entry["available_at"],"target_at":target,
                "actual_observation_id":label["bike"].id,"actual_time":label["bike"].sampled_at,
                "label_available_at":label["available_at"],"actual_bikes":label["bike"].available_bikes,
                "baseline":b.available_bikes,"features":features,
                "target_offset_seconds":(label["bike"].sampled_at-target).total_seconds()})
    result.sort(key=lambda e:(e["feature_cutoff"],e["station_id"],e["input_observation_id"]))
    return result, dict(excluded)
