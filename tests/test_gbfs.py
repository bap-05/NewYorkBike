"""Constructed protocol fixtures only; never application data or database seeds."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from ingestion.clients.citibike_client import CitiBikeClient, gbfs_timestamp
from ingestion.clients.http import SourceError
from ingestion.normalizer import normalize_station
from shared.models import Station
from shared.time import UTC, display_time


def client_fixture(settings, now, info, status, *, version="1.1", discovery_override=None, status_change=None):
    stamp = now.isoformat() if version == "3.0" else int(now.timestamp())
    feeds = [{"name": "station_information", "url": "https://feeds.test.invalid/dynamic-info"},
             {"name": "station_status", "url": "https://feeds.test.invalid/dynamic-status"}]
    discovery = {"version": version, "last_updated": stamp, "ttl": 60,
                 "data": {"feeds": feeds} if version == "3.0" else {"en": {"feeds": feeds}}}
    envelope = lambda row: {"version": version, "last_updated": stamp, "ttl": 60, "data": {"stations": row}}
    payloads = {settings.gbfs_discovery_url: discovery_override or discovery,
                feeds[0]["url"]: envelope([info]), feeds[1]["url"]: envelope([status])}
    if status_change:
        payloads[feeds[1]["url"]].update(status_change)
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=payloads[str(request.url)])
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return CitiBikeClient(http, settings), http, calls


@pytest.mark.parametrize("version", ["1.1", "2.0", "2.3"])
def test_discovery_and_join_preserve_string_ids(settings, now, station_row, station_status, version):
    station_row["station_id"] = station_status["station_id"] = "00017"
    client, http, calls = client_fixture(settings, now, station_row, station_status, version=version)
    with http:
        row, = client.fetch(["00017"])
    assert row.station_id == "00017" and row.available_bikes == 7
    assert row.capacity == 5 and row.available_docks == 2
    assert row.latitude == 40.75 and float(row.longitude) == -73.99
    assert row.source_observed_at == now - timedelta(seconds=60)
    assert calls[1:] == ["https://feeds.test.invalid/dynamic-info", "https://feeds.test.invalid/dynamic-status"]


def test_missing_status_does_not_invent_zero(settings, now, station_row, station_status):
    station_status["station_id"] = "DIFFERENT-STATION"
    client, http, _ = client_fixture(settings, now, station_row, station_status)
    with http:
        row, = client.fetch()
    assert row.available_bikes is None and row.quality_status == "missing"


@pytest.mark.parametrize("change,quality", [({"is_renting": 0}, "inactive"), ({"is_installed": 0}, "inactive"),
    ({"last_reported": 1}, "stale"), ({"num_bikes_available": -1}, "invalid"),
    ({"num_bikes_available": None}, "missing"), ({"last_reported": "2026-01-01T00:00:00Z"}, "invalid")])
def test_station_quality(settings, now, station_row, station_status, change, quality):
    station_status.update(change)
    client, http, _ = client_fixture(settings, now, station_row, station_status)
    with http:
        row, = client.fetch()
    assert row.quality_status == quality


def test_stale_status_feed_rejected(settings, now, station_row, station_status):
    client, http, _ = client_fixture(settings, now, station_row, station_status,
                                    status_change={"last_updated": int(now.timestamp()) - 3600})
    with http, pytest.raises(SourceError, match="stale"):
        client.fetch()


def test_unknown_version_rejected(settings, now, station_row, station_status):
    client, http, _ = client_fixture(settings, now, station_row, station_status, version="9.0")
    with http, pytest.raises(SourceError, match="unsupported"):
        client.fetch()


def test_mismatched_child_version_rejected(settings, now, station_row, station_status):
    client, http, _ = client_fixture(settings, now, station_row, station_status, status_change={"version": "2.3"})
    with http, pytest.raises(SourceError, match="versions differ"):
        client.fetch()


def test_missing_required_discovery_feed(settings, now, station_row, station_status):
    payload = {"version": "1.1", "ttl": 60, "last_updated": int(now.timestamp()), "data": {"en": {"feeds": []}}}
    client, http, _ = client_fixture(settings, now, station_row, station_status, discovery_override=payload)
    with http, pytest.raises(SourceError, match="required feeds"):
        client.fetch()


def test_version_three_uses_iso_time_and_vehicles(settings, now, station_row, station_status):
    station_row["name"] = [{"language": "en", "text": "Test only"}]
    station_status["last_reported"] = now.isoformat()
    station_status["num_vehicles_available"] = 8
    client, http, _ = client_fixture(settings, now, station_row, station_status, version="3.0")
    with http:
        row, = client.fetch()
    assert row.available_bikes == 8 and row.source_observed_at == now


def test_dst_fall_back_disambiguated():
    first = datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    second = datetime(2026, 11, 1, 6, 30, tzinfo=UTC)
    assert display_time(first).endswith("01:30:00-04:00")
    assert display_time(second).endswith("01:30:00-05:00")
    assert first.astimezone(ZoneInfo("America/New_York")).fold == 0
    assert second.astimezone(ZoneInfo("America/New_York")).fold == 1


def test_dst_spring_forward():
    assert display_time(datetime(2026, 3, 8, 6, 59, tzinfo=UTC)).endswith("01:59:00-05:00")
    assert display_time(datetime(2026, 3, 8, 7, 0, tzinfo=UTC)).endswith("03:00:00-04:00")


def test_source_identity_allows_same_station_id(session, now):
    for source in ("seoul", "citibike"):
        session.add(Station(source=source, station_id="same-id", name="Test only", latitude=40.75,
                            longitude=-73.99, updated_at=now, rack_count=10 if source == "seoul" else None))
    session.commit()
    assert session.get(Station, ("seoul", "same-id")).rack_count == 10
    assert session.get(Station, ("citibike", "same-id")).capacity is None


@pytest.mark.parametrize("value,version", [("2026-01-01T00:00:00", "3.0"), (123, "3.0"),
    ("123", "1.1"), (True, "1.1"), (float("nan"), "2.3")])
def test_timestamp_format_follows_version(value, version):
    with pytest.raises(SourceError):
        gbfs_timestamp(value, version)
