from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return value.astimezone(UTC)


def sampling_slot(value: datetime) -> datetime:
    value = as_utc(value)
    return value.replace(minute=value.minute // 5 * 5, second=0, microsecond=0)


def display_time(value: datetime, timezone_name: str = "America/New_York") -> str:
    return as_utc(value).astimezone(ZoneInfo(timezone_name)).isoformat()


def collection_instant(value: datetime) -> datetime:
    """An immediate sample uses its actual start second, not the preceding half-hour."""
    return as_utc(value).replace(microsecond=0)


def next_half_hour(value: datetime, timezone_name: str = "America/New_York") -> datetime:
    """Next local :00/:30 strictly after value, including both DST repeated hours."""
    instant = as_utc(value)
    zone = ZoneInfo(timezone_name)
    candidate = instant.replace(second=0, microsecond=0) + timedelta(minutes=1)
    # Advance real UTC instants rather than adding local wall time across DST changes.
    while candidate.astimezone(zone).minute not in (0, 30):
        candidate += timedelta(minutes=1)
    return candidate
