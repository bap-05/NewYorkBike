from datetime import datetime

from ingestion.clients.http import SourceError, get_json
from ingestion.normalizer import coordinate, count, number
from shared.time import UTC, utcnow

VARIABLES = ("temperature_2m", "relative_humidity_2m", "rain", "wind_speed_10m")
EXPECTED_UNITS = dict(zip(VARIABLES, ("°C", "%", "mm", "m/s")))


class WeatherClient:
    def __init__(self, client, settings):
        self.client, self.settings = client, settings

    def fetch(self, latitude, longitude) -> dict:
        s = self.settings
        payload = get_json(self.client, s.weather_url, source="open-meteo", attempts=s.max_attempts,
                           backoff=s.backoff_seconds, params={
                               "latitude": str(latitude), "longitude": str(longitude),
                               "current": ",".join(VARIABLES), "timezone": "UTC", "timeformat": "unixtime",
                               "temperature_unit": "celsius", "wind_speed_unit": "ms", "precipitation_unit": "mm"})
        collected_at = utcnow()
        current, units = payload.get("current"), payload.get("current_units")
        if payload.get("error") or not isinstance(current, dict) or not isinstance(units, dict):
            raise SourceError("open-meteo: missing current data or API error")
        if any(units.get(key) != expected for key, expected in EXPECTED_UNITS.items()):
            raise SourceError("open-meteo: unexpected weather units")
        epoch = number(current.get("time"))
        interval, quality = count(current.get("interval"))
        if epoch is None or quality != "valid" or not interval:
            raise SourceError("open-meteo: invalid time or interval")
        try:
            weather_time = datetime.fromtimestamp(epoch, UTC)
            returned_latitude = coordinate(payload["latitude"]) if payload.get("latitude") is not None else None
            returned_longitude = coordinate(payload["longitude"], False) if payload.get("longitude") is not None else None
        except (ValueError, OverflowError, OSError):
            raise SourceError("open-meteo: invalid time or grid coordinates") from None
        # A source time in the future must never become an input available in the past.
        age = (collected_at - weather_time).total_seconds()
        if age < 0 or age > s.weather_max_age_seconds:
            raise SourceError("open-meteo: future or stale weather time")
        return dict(requested_latitude=latitude, requested_longitude=longitude,
                    returned_latitude=returned_latitude, returned_longitude=returned_longitude,
                    weather_time=weather_time, collected_at=collected_at,
                    temperature=number(current.get("temperature_2m")),
                    humidity=number(current.get("relative_humidity_2m"), 0, 100),
                    rain=number(current.get("rain"), 0), wind_speed=number(current.get("wind_speed_10m"), 0),
                    units={key: units[key] for key in VARIABLES}, interval_seconds=interval, source="open-meteo")
