"""Pure window statistics. Missing observations are never synthesized or filled."""
from datetime import datetime, time, timedelta
from decimal import Decimal
import math
from statistics import fmean, pstdev
from zoneinfo import ZoneInfo

from shared.time import UTC, as_utc


def period_start(value, seconds):
    value = as_utc(value)
    return datetime.fromtimestamp(int(value.timestamp()) // seconds * seconds, UTC)


def analysis_start(cutoff, options):
    zone = ZoneInfo(options.timezone_name)
    day = cutoff.astimezone(zone).date() - timedelta(days=options.window_days - 1)
    return datetime.combine(day, time.min, zone).astimezone(UTC)


def windows(cutoff, options):
    """Fixed hourly UTC identities and New York days, including 23/25-hour days."""
    start = analysis_start(cutoff, options)
    zone = ZoneInfo(options.timezone_name)
    result = []
    current = start
    while current < cutoff:
        result.append(("hour", current, current + timedelta(hours=1)))
        current += timedelta(hours=1)
    day = start.astimezone(zone).date()
    while True:
        begin = datetime.combine(day, time.min, zone).astimezone(UTC)
        if begin >= cutoff:
            break
        end = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(UTC)
        result.append(("day", begin, end))
        day += timedelta(days=1)
    return result


def usable_bike(bike):
    return (bike.quality_status == "valid" and bike.available_bikes is not None
            and bike.available_bikes >= 0 and bike.is_installed is True and bike.is_renting is True)


def usable_weather(weather, bike, station, cutoff, options, max_age, weather_published):
    if weather is None or not weather_published or weather.source != "open-meteo":
        return False
    values = (weather.temperature, weather.humidity, weather.rain, weather.wind_speed)
    if any(value is None or not math.isfinite(value) for value in values):
        return False
    units = {"temperature_2m": "\u00b0C", "relative_humidity_2m": "%", "rain": "mm", "wind_speed_10m": "m/s"}
    return (all((weather.units or {}).get(key) == unit for key, unit in units.items())
            and Decimal(str(weather.requested_latitude)) == Decimal(str(station.latitude))
            and Decimal(str(weather.requested_longitude)) == Decimal(str(station.longitude))
            and weather.collected_at <= cutoff and weather.weather_time <= cutoff
            and 0 <= (bike.collected_at - weather.weather_time).total_seconds() <= max_age
            and bool(weather.interval_seconds and weather.interval_seconds > 0)
            and 0 <= weather.humidity <= 100 and weather.rain >= 0 and weather.wind_speed >= 0)


def summarize(entries, *, station, first_observation, aggregation, start, end,
              cutoff, options, weather_max_age):
    """Entries are (bike, weather, collection_finished_at, weather_is_published)."""
    interval = options.expected_interval_seconds
    latest = {}
    for entry in entries:
        bike = entry[0]
        key = period_start(bike.sampled_at, interval)
        previous = latest.get(key)
        if previous is None or (bike.sampled_at, bike.collected_at, bike.id) > (
                previous[0].sampled_at, previous[0].collected_at, previous[0].id):
            latest[key] = entry
    ordered = [latest[key] for key in sorted(latest)]
    expected = set()
    current = max(start, period_start(first_observation, interval))
    due_before = cutoff - timedelta(seconds=options.ingestion_grace_seconds)
    while current < end and current <= due_before:
        expected.add(current)
        current += timedelta(seconds=interval)
    # An already received startup/manual sample also represents its real slot.
    expected.update(latest)
    valid = [entry for entry in ordered if usable_bike(entry[0])]
    counts = [entry[0].available_bikes for entry in valid]
    coverage = len(valid) / len(expected) if expected else None
    paired = [entry for entry in valid if usable_weather(entry[1], entry[0], station, cutoff,
              options, weather_max_age, entry[3])]
    unique_weather = {entry[1].id: entry[1] for entry in paired}
    weather = list(unique_weather.values())
    changes = []
    previous = None
    for bike, *_ in ordered:
        if not usable_bike(bike):
            previous = None
            continue
        if previous is not None and (bike.sampled_at - previous.sampled_at).total_seconds() <= interval * 1.5:
            changes.append(abs(bike.available_bikes - previous.available_bikes))
        previous = bike
    mean = lambda values: fmean(values) if values else None
    ratio = lambda values: fmean(values) if values else None
    rain_bikes = [b.available_bikes for b,w,*_ in paired if w.rain > 0]
    dry_bikes = [b.available_bikes for b,w,*_ in paired if w.rain == 0]
    correlation = None
    if len(paired) >= 3 and len(weather) >= 3:
        xs = [w.temperature for b,w,*_ in paired]
        ys = [b.available_bikes for b,w,*_ in paired]
        mx, my = fmean(xs), fmean(ys)
        denominator = math.sqrt(sum((x-mx)**2 for x in xs) * sum((y-my)**2 for y in ys))
        if denominator:
            correlation = max(-1.0, min(1.0, sum((x-mx)*(y-my) for x,y in zip(xs,ys)) / denominator))
    metrics = {
        "available_bikes_mean": (mean(counts), len(counts), "bikes"),
        "available_bikes_min": (min(counts) if counts else None, len(counts), "bikes"),
        "available_bikes_max": (max(counts) if counts else None, len(counts), "bikes"),
        "available_bikes_stddev": (pstdev(counts) if len(counts) >= 2 else None, len(counts), "bikes"),
        "empty_ratio": (ratio([n == 0 for n in counts]), len(counts), "ratio"),
        "low_bikes_ratio": (ratio([1 <= n <= options.low_bike_threshold for n in counts]), len(counts), "ratio"),
        "mean_absolute_change": (mean(changes), len(changes), "bikes_per_adjacent_pair"),
        "inactive_ratio": (ratio([b.quality_status == "inactive" for b,*_ in ordered]), len(ordered), "ratio"),
        "stale_ratio": (ratio([b.quality_status == "stale" for b,*_ in ordered]), len(ordered), "ratio"),
        "unusable_ratio": (ratio([not usable_bike(b) for b,*_ in ordered]), len(ordered), "ratio"),
        "missing_slot_ratio": (len(expected - latest.keys()) / len(expected) if expected else None, len(expected), "ratio"),
        "missing_weather_ratio": (1 - len(paired)/len(valid) if valid else None, len(valid), "ratio"),
        "temperature_mean_c": (mean([w.temperature for w in weather]), len(weather), "\u00b0C"),
        "humidity_mean_pct": (mean([w.humidity for w in weather]), len(weather), "%"),
        "rain_rate_mean_mm_h": (mean([w.rain*3600/w.interval_seconds for w in weather]), len(weather), "mm/h"),
        "wind_speed_mean_m_s": (mean([w.wind_speed for w in weather]), len(weather), "m/s"),
        "available_bikes_mean_rain": (mean(rain_bikes), len(rain_bikes), "bikes"),
        "available_bikes_mean_dry": (mean(dry_bikes), len(dry_bikes), "bikes"),
        "temperature_bikes_correlation": (correlation, len(paired), "Pearson_r"),
    }
    local = start.astimezone(ZoneInfo(options.timezone_name))
    dimensions = {"timezone": options.timezone_name, "local_start": local.isoformat(),
                  "local_weekday": local.weekday(), "local_hour": local.hour if aggregation == "hour" else None}
    watermark = max((entry[2] for entry in entries), default=None)
    output = []
    for name, (value, count, unit) in metrics.items():
        quality = "ok"
        if value is None or count < options.min_samples:
            quality = "insufficient_data"
        elif coverage is None or coverage < options.min_coverage:
            quality = "low_coverage"
        output.append({"source": station.source, "station_id": station.station_id,
            "window_start": start, "window_end": end, "aggregation": aggregation,
            "metric_name": name, "metric_value": value, "sample_count": count,
            "observed_sample_count": len(entries), "expected_sample_count": len(expected),
            "coverage": coverage, "quality_status": quality,
            "dimensions": {**dimensions, "unit": unit}, "input_cutoff": cutoff,
            "input_watermark": watermark})
    return output
