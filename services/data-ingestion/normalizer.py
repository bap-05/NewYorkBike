from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from math import isfinite
from datetime import datetime


def number(value, minimum=None, maximum=None):
    if value is None or isinstance(value, bool) or str(value).strip() == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not isfinite(result) or (minimum is not None and result < minimum) or (maximum is not None and result > maximum):
        return None
    return result


def count(value):
    if value is None or isinstance(value, bool) or str(value).strip() == "":
        return None, "missing"
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or result > 2147483647 or result != result.to_integral_value():
            return None, "invalid"
        return int(result), "valid"
    except (InvalidOperation, ValueError):
        return None, "invalid"


def coordinate(value, latitude=True):
    result = number(value, -90 if latitude else -180, 90 if latitude else 180)
    if result is None:
        raise ValueError("Missing or invalid coordinates")
    return Decimal(str(result)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class NormalizedStation:
    station_id: str
    name: str
    latitude: Decimal
    longitude: Decimal
    capacity: int | None
    available_bikes: int | None
    available_docks: int | None
    quality_status: str
    is_installed: bool | None
    is_renting: bool | None
    is_returning: bool | None
    source_observed_at: datetime | None
    collected_at: datetime
    feed_last_updated: datetime
    information_updated_at: datetime
    gbfs_version: str


def flag(value):
    if isinstance(value, bool):
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    return None


def normalize_station(row: dict, status: dict | None, *, version, collected_at,
                      feed_last_updated, information_updated_at, max_age) -> NormalizedStation:
    # Local import avoids a module-level cycle between parser and normalizer.
    from ingestion.clients.citibike_client import gbfs_timestamp
    from ingestion.clients.http import SourceError
    station_id, name = row.get("station_id"), row.get("name")
    if not isinstance(station_id, str) or not station_id.strip() or len(station_id) > 128:
        raise ValueError("Invalid station_id")
    if version == "3.0" and isinstance(name, list):
        name = next((item.get("text") for item in name if isinstance(item, dict) and item.get("language") == "en"), None)
    if not isinstance(name, str) or not name.strip() or len(name) > 255:
        raise ValueError("Missing or invalid station name")
    latitude = coordinate(row.get("lat"))
    longitude = coordinate(row.get("lon"), latitude=False)
    if latitude == 0 and longitude == 0:
        raise ValueError("Unusable station coordinates (0,0)")
    capacity, _ = count(row.get("capacity"))
    status = status or {}
    bikes, quality = count(status.get("num_vehicles_available" if version == "3.0" else "num_bikes_available"))
    docks, docks_quality = count(status.get("num_docks_available"))
    installed, renting, returning = (flag(status.get(key)) for key in ("is_installed", "is_renting", "is_returning"))
    observed = None
    try:
        observed = gbfs_timestamp(status.get("last_reported"), version)
    except SourceError:
        quality = "missing" if status.get("last_reported") is None else "invalid"
    if quality == "valid" and (docks_quality != "valid" or None in (installed, renting, returning)):
        quality = "missing" if docks_quality == "missing" or None in (installed, renting, returning) else "invalid"
    if quality == "valid" and observed is not None:
        age = (collected_at - observed).total_seconds()
        if age < -60 or age > max_age:
            quality = "stale"
    if installed is False or renting is False:
        quality = "inactive"
    return NormalizedStation(station_id, name, latitude, longitude, capacity, bikes, docks,
        quality, installed, renting, returning, observed, collected_at, feed_last_updated,
        information_updated_at, version)
