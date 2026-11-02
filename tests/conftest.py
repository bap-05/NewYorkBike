"""Test-only constructed API responses, never seeds or application data."""
from datetime import datetime, timezone
from dataclasses import replace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from shared.config import Settings
from shared.models import Base


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("STATION_IDS", "TEST-STATION")
    monkeypatch.setenv("OUTBOUND_PROXY_ENABLED", "false")
    monkeypatch.setenv("OUTBOUND_PROXY_URLS", "[]")
    monkeypatch.setenv("DISPLAY_TIMEZONE", "America/New_York")
    return replace(Settings.load(), backoff_seconds=0)


@pytest.fixture
def now(monkeypatch):
    value = datetime(2026, 1, 1, 12, 2, tzinfo=timezone.utc)
    for module in ("ingestion.collector", "ingestion.clients.citibike_client", "ingestion.clients.weather_client"):
        monkeypatch.setattr(f"{module}.utcnow", lambda: value)
    return value


@pytest.fixture
def session():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def station_row():
    return {"station_id": "TEST-STATION", "name": "Test station (unit test only)",
            "lat": 40.75, "lon": -73.99, "capacity": 5}


@pytest.fixture
def station_status(now):
    return {"station_id": "TEST-STATION", "num_bikes_available": 7, "num_docks_available": 2,
            "is_installed": 1, "is_renting": 1, "is_returning": 1,
            "last_reported": int(now.timestamp()) - 60}


@pytest.fixture
def weather_payload(now):
    return {"latitude": 40.75, "longitude": -73.99,
            "current": {"time": int(now.replace(minute=0).timestamp()), "interval": 900,
                        "temperature_2m": 12.5, "relative_humidity_2m": 70, "rain": 0, "wind_speed_10m": 2},
            "current_units": {"temperature_2m": "°C", "relative_humidity_2m": "%", "rain": "mm", "wind_speed_10m": "m/s"}}
