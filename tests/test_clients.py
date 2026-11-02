import httpx
import pytest

from ingestion.clients.http import SourceError, get_json
from ingestion.clients.weather_client import WeatherClient
from ingestion.normalizer import count


@pytest.mark.parametrize("value,expected", [(None, (None, "missing")), ("", (None, "missing")),
    ("0", (0, "valid")), ("-1", (None, "invalid")), ("NaN", (None, "invalid")),
    ("1.2", (None, "invalid")), ("bad", (None, "invalid")), ("2147483648", (None, "invalid"))])
def test_counts_keep_missing_distinct_from_zero(value, expected):
    assert count(value) == expected


def test_bounded_retries():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(SourceError, match="HTTP 503"):
            get_json(http, "https://test.invalid", source="test", attempts=3, backoff=0)
    assert len(calls) == 3


def test_invalid_json():
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, text="<xml/>"))) as http:
        with pytest.raises(SourceError, match="invalid JSON"):
            get_json(http, "https://test.invalid", source="test")


def test_weather_preserves_nulls_and_units(settings, weather_payload, now):
    weather_payload["current"]["rain"] = None

    def handler(request):
        assert request.url.params["timezone"] == "UTC"
        assert request.url.params["wind_speed_unit"] == "ms"
        return httpx.Response(200, json=weather_payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        data = WeatherClient(http, settings).fetch(40.75, -73.99)
    assert data["rain"] is None
    assert data["interval_seconds"] == 900
    assert data["weather_time"].tzinfo == now.tzinfo


@pytest.mark.parametrize("delta", [-7200, 3600])
def test_weather_rejects_stale_and_future_time(settings, weather_payload, now, delta):
    weather_payload["current"]["time"] = int(now.timestamp()) + delta
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=weather_payload))) as http:
        with pytest.raises(SourceError, match="future or stale"):
            WeatherClient(http, settings).fetch(40.75, -73.99)
