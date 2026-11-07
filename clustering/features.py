"""Read-only feature extraction; no API calls, imputation or Analysis dependency."""
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from statistics import fmean, pstdev
from zoneinfo import ZoneInfo

from sqlalchemy import select

from shared.models import BikeObservation, Station
from shared.repositories.silver import bike_observations
from shared.time import UTC, as_utc

FEATURE_NAMES = ["mean_availability_ratio", "std_availability_ratio", "mean_abs_change_ratio",
                 "empty_ratio", "low_bikes_ratio", "night_ratio", "morning_ratio",
                 "daytime_ratio", "evening_ratio"]
BLOCKS = ((0, 6), (6, 10), (10, 16), (16, 24))


def bounds(instant, options):
    day = as_utc(instant).astimezone(ZoneInfo(options.timezone_name)).date()
    zone = ZoneInfo(options.timezone_name)
    end = datetime.combine(day, time.min, zone).astimezone(UTC)
    start = datetime.combine(day - timedelta(days=options.window_days), time.min, zone).astimezone(UTC)
    return day, start, end


def slot(instant, seconds):
    return datetime.fromtimestamp(int(as_utc(instant).timestamp()) // seconds * seconds, UTC)


def calculate_features(session, settings, options, instant):
    day, start, end = bounds(instant, options)
    query = select(Station).where(Station.source == settings.bike_source)
    query = query.where(Station.station_id.in_(settings.station_ids)) if settings.station_ids else query.where(Station.is_monitored.is_(True))
    stations = list(session.scalars(query.order_by(Station.station_id)))
    ids = [s.station_id for s in stations]
    # Freeze availability at midnight, even if this worker is run later that day.
    rows = list(session.scalars(bike_observations(source=settings.bike_source, available_at=end,
        include_unusable=True).where(BikeObservation.station_id.in_(ids),
        BikeObservation.sampled_at >= start, BikeObservation.sampled_at < end)
        .order_by(BikeObservation.collected_at, BikeObservation.id)))
    zone = ZoneInfo(options.timezone_name)
    seconds = options.expected_interval_seconds
    expected = Counter()
    cursor = start
    while cursor < end:
        expected[cursor.astimezone(zone).date().isoformat()] += 1
        cursor += timedelta(seconds=seconds)
    by_station = defaultdict(dict)
    for row in rows:
        # Last collected observation in each slot wins, including inactive/invalid.
        by_station[row.station_id][slot(row.sampled_at, seconds)] = row
    features, rejected = [], []
    for station in stations:
        valid, daily, invalid = [], Counter(), Counter()
        capacity = station.capacity
        for tick, row in sorted(by_station[station.station_id].items()):
            usable = (row.quality_status == "valid" and row.available_bikes is not None
                and row.is_installed is True and row.is_renting is True
                and capacity is not None and capacity > 0 and 0 <= row.available_bikes <= capacity)
            if not usable:
                invalid[row.quality_status if row.quality_status != "valid" else "invalid_flags_count_or_capacity"] += 1
                continue
            valid.append((tick, row.available_bikes))
            daily[tick.astimezone(zone).date().isoformat()] += 1
        coverage = {date: daily[date] / count for date, count in expected.items()}
        hourly = defaultdict(list)
        for tick, count in valid:
            hourly[tick.astimezone(zone).hour].append(count)
        changes = [abs(b[1] - a[1]) for a, b in zip(valid, valid[1:])
                   if 0 < (b[0] - a[0]).total_seconds() <= seconds * 1.5]
        reasons = []
        if capacity is None or capacity <= 0:
            reasons.append("missing_positive_capacity")
        if len(valid) < options.min_samples:
            reasons.append("too_few_samples")
        if any(value < options.min_daily_coverage for value in coverage.values()):
            reasons.append("incomplete_daily_coverage")
        if any(len(hourly[h]) < 2 for h in range(24)):
            reasons.append("incomplete_hourly_profile")
        if not changes:
            reasons.append("no_adjacent_samples")
        audit = {"station_id": station.station_id, "name": station.name,
            "sample_count": len(valid), "expected_sample_count": sum(expected.values()),
            "coverage": len(valid) / sum(expected.values()), "daily_coverage": coverage,
            "excluded_samples": dict(invalid), "capacity": capacity,
            "hourly_mean_bikes": {str(h): fmean(hourly[h]) if hourly[h] else None for h in range(24)}}
        if reasons:
            rejected.append({**audit, "reasons": reasons})
            continue
        counts = [count for _, count in valid]
        vector = [fmean(counts) / capacity, pstdev(counts) / capacity, fmean(changes) / capacity,
            sum(c == 0 for c in counts) / len(counts),
            sum(0 < c <= options.low_bike_threshold for c in counts) / len(counts)]
        for low, high in BLOCKS:
            vector.append(fmean(count for tick, count in valid if low <= tick.astimezone(zone).hour < high) / capacity)
        features.append({**audit, "feature_values": dict(zip(FEATURE_NAMES, vector)),
            "raw_statistics": {"mean_bikes": fmean(counts), "std_bikes": pstdev(counts),
                "mean_abs_change_bikes": fmean(changes), "min_bikes": min(counts), "max_bikes": max(counts)},
            "metadata_snapshot": {"name": station.name, "latitude": float(station.latitude),
                "longitude": float(station.longitude), "capacity": capacity,
                "metadata_updated_at": station.updated_at.isoformat(),
                "capacity_policy": "current_metadata_snapshot_not_historical_capacity"}})
    known = set(ids)
    for missing in sorted(set(settings.station_ids) - known):
        rejected.append({"station_id": missing, "reasons": ["missing_station_metadata"]})
    return features, {"run_date": day.isoformat(), "window_start": start.isoformat(),
        "window_end": end.isoformat(), "input_cutoff": end.isoformat(),
        "input_watermark": max((r.collected_at for r in rows), default=None),
        "input_rows": len(rows), "station_count": len(stations), "eligible_stations": len(features),
        "minimum_stations": options.min_stations, "rejected_stations": rejected,
        "expected_samples_per_station": sum(expected.values())}
