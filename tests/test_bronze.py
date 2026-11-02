"""Constructed responses in temporary directories; no API calls or production seeds."""
from datetime import timedelta
import json

import httpx
import pytest
from sqlalchemy import func, select

from ingestion.bronze import BronzeArchive, BronzeError, RecordingClient
from ingestion.clients.citibike_client import CitiBikeClient
from ingestion.clients.http import SourceError, get_json
from ingestion.clients.weather_client import WeatherClient
from ingestion.collector import collect_once
from scripts.inspect_bronze import verify_manifest
from shared.models import BikeObservation, CollectionRun
from shared.time import sampling_slot


def start(archive, now):
    return archive.begin(run_id=1, attempt_count=1, scheduled_at=sampling_slot(now),
                         source="citibike", station_ids=("TEST-STATION",))


def source_clients(settings, now, station_row, station_status, weather_payload, archive, weather_fail=None):
    stamp = int(now.timestamp())
    feeds = [{"name": "station_information", "url": "https://test.invalid/info"},
             {"name": "station_status", "url": "https://test.invalid/status"}]
    def envelope(data):
        return {"version": "1.1", "ttl": 60, "last_updated": stamp, "data": data}
    def handler(request):
        url = str(request.url.copy_with(query=None))
        if url == settings.gbfs_discovery_url:
            payload = envelope({"en": {"feeds": feeds}})
        elif url == feeds[0]["url"]:
            payload = envelope({"stations": [station_row]})
        elif url == feeds[1]["url"]:
            payload = envelope({"stations": [station_status]})
        else:
            assert url == settings.weather_url
            if weather_fail and weather_fail[0]:
                return httpx.Response(503, json={"error": "test-only source unavailable"})
            payload = weather_payload
        return httpx.Response(200, json=payload)
    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = RecordingClient(http, archive)
    return CitiBikeClient(client, settings), WeatherClient(client, settings), http


def test_bodies_preserved_before_parsing_and_metadata_redacted(tmp_path, now):
    archive = BronzeArchive(tmp_path)
    relative = start(archive, now)
    raw = b'{\n  "value": null, "zero": 0\n}\n'
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=raw))) as http:
        assert get_json(RecordingClient(http, archive), "https://user:private@test.invalid/feed?token=private",
                        source="citibike") == {"value": None, "zero": 0}
    archive.finish("complete", planned_silver_status="success")
    manifest = tmp_path / relative
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert "private" not in manifest.read_text(encoding="utf-8")
    assert data["responses"][0]["url"] == "https://test.invalid/feed"
    assert (manifest.parent / data["responses"][0]["body_file"]).read_bytes() == raw
    assert verify_manifest(manifest)["verified_bodies"] == 1


def test_invalid_json_is_kept_as_raw_evidence(tmp_path, now):
    archive = BronzeArchive(tmp_path)
    path = start(archive, now)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b'<bad-json>'))) as http:
        with pytest.raises(SourceError, match="invalid JSON"):
            get_json(RecordingClient(http, archive), "https://test.invalid/feed", source="citibike")
    archive.finish("complete", planned_silver_status="failed")
    result = verify_manifest(tmp_path / path)
    assert result["verified_bodies"] == 1 and result["json_bodies"] == 0


def test_every_http_retry_is_preserved(tmp_path, now):
    archive = BronzeArchive(tmp_path)
    path = start(archive, now)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) == 1 else 200, json={"attempt": len(calls)})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        get_json(RecordingClient(http, archive), "https://test.invalid/feed", source="citibike", backoff=0)
    archive.finish("complete")
    document = json.loads((tmp_path / path).read_text(encoding="utf-8"))
    assert [r["http_status"] for r in document["responses"]] == [503, 200]
    assert len({r["body_file"] for r in document["responses"]}) == 2


def test_network_error_stores_no_exception_secret(tmp_path, now):
    archive = BronzeArchive(tmp_path)
    path = start(archive, now)
    def handler(request):
        raise httpx.ConnectError("test-private-proxy-password", request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(SourceError):
            get_json(RecordingClient(http, archive), "https://test.invalid/feed", source="citibike", attempts=1)
    archive.finish("complete", planned_silver_status="failed")
    text = (tmp_path / path).read_text(encoding="utf-8")
    assert "test-private-proxy-password" not in text
    assert verify_manifest(tmp_path / path)["network_failures"] == 1


def test_proxy_auth_body_is_not_source_data(tmp_path, now):
    archive = BronzeArchive(tmp_path)
    path = start(archive, now)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(407, text="test-private-password"))) as http:
        with pytest.raises(SourceError, match="407"):
            get_json(RecordingClient(http, archive), "https://test.invalid/feed", source="citibike")
    archive.finish("complete", planned_silver_status="failed")
    assert verify_manifest(tmp_path / path)["verified_bodies"] == 0
    assert "test-private-password" not in (tmp_path / path).read_text(encoding="utf-8")


def test_integrity_check_detects_modified_body(tmp_path, now):
    archive = BronzeArchive(tmp_path)
    path = start(archive, now)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"test": True}))) as http:
        get_json(RecordingClient(http, archive), "https://test.invalid/feed", source="citibike")
    archive.finish("complete")
    manifest = tmp_path / path
    entry = json.loads(manifest.read_text(encoding="utf-8"))["responses"][0]
    (manifest.parent / entry["body_file"]).write_bytes(b'changed test file')
    with pytest.raises(ValueError, match="integrity"):
        verify_manifest(manifest)


def test_run_reference_and_idempotency(session, settings, now, station_row, station_status, weather_payload, tmp_path):
    archive = BronzeArchive(tmp_path)
    bike, weather, http = source_clients(settings, now, station_row, station_status, weather_payload, archive)
    with http:
        run = collect_once(session, bike, weather, settings.station_ids, bronze=archive)
        path = run.bronze_manifest_path
        assert verify_manifest(tmp_path / path)["response_count"] == 4
        again = collect_once(session, bike, weather, settings.station_ids, bronze=archive)
    assert run.status == "success" and again.bronze_manifest_path == path
    assert len(list(tmp_path.rglob("manifest.json"))) == 1


def test_failed_silver_keeps_bronze(session, settings, now, station_row, station_status, weather_payload, tmp_path):
    archive = BronzeArchive(tmp_path)
    bike, weather, http = source_clients(settings, now, station_row, station_status, weather_payload, archive)
    def crash(*args):
        raise RuntimeError("test-only failure after GBFS capture")
    weather.fetch = crash
    with http, pytest.raises(RuntimeError):
        collect_once(session, bike, weather, settings.station_ids, bronze=archive)
    run = session.scalar(select(CollectionRun))
    assert run.status == "failed"
    assert session.scalar(select(func.count()).select_from(BikeObservation)) == 0
    result = verify_manifest(tmp_path / run.bronze_manifest_path)
    assert result["capture_status"] == "aborted" and result["verified_bodies"] == 3


def test_storage_failure_stops_silver_publication(session, settings, now, station_row, station_status,
                                                 weather_payload, tmp_path, monkeypatch):
    archive = BronzeArchive(tmp_path)
    original = archive._save_manifest
    def disk_full():
        if archive.active:
            raise OSError("test-only disk full")
        original()
    monkeypatch.setattr(archive, "_save_manifest", disk_full)
    bike, weather, http = source_clients(settings, now, station_row, station_status, weather_payload, archive)
    with http, pytest.raises(BronzeError):
        collect_once(session, bike, weather, settings.station_ids, bronze=archive)
    assert session.scalar(select(func.count()).select_from(BikeObservation)) == 0
    assert session.scalar(select(CollectionRun)).status == "failed"


def test_collection_retry_has_new_manifest_without_rewriting_raw(session, settings, now, station_row,
                                                               station_status, weather_payload, tmp_path):
    archive = BronzeArchive(tmp_path)
    fail = [True]
    bike, weather, http = source_clients(settings, now, station_row, station_status, weather_payload, archive, fail)
    with http:
        first = collect_once(session, bike, weather, settings.station_ids, bronze=archive)
        original_path = tmp_path / first.bronze_manifest_path
        original_bytes = original_path.read_bytes()
        fail[0] = False
        second = collect_once(session, bike, weather, settings.station_ids, bronze=archive)
    assert second.status == "success" and second.attempt_count == 2
    assert tmp_path / second.bronze_manifest_path != original_path
    assert original_path.read_bytes() == original_bytes
    assert verify_manifest(tmp_path / second.bronze_manifest_path)["response_count"] == 1


def test_fresh_weather_reuse_records_original_run(session, settings, now, station_row, station_status,
                                                 weather_payload, tmp_path, monkeypatch):
    archive = BronzeArchive(tmp_path)
    bike, weather, http = source_clients(settings, now, station_row, station_status, weather_payload, archive)
    with http:
        first = collect_once(session, bike, weather, settings.station_ids, bronze=archive)
    later = now + timedelta(minutes=5)
    for module in ("ingestion.collector", "ingestion.clients.citibike_client", "ingestion.clients.weather_client"):
        monkeypatch.setattr(f"{module}.utcnow", lambda: later)
    bike, weather, http = source_clients(settings, later, station_row, station_status, weather_payload, archive)
    with http:
        second = collect_once(session, bike, weather, settings.station_ids, bronze=archive)
    manifest = json.loads((tmp_path / second.bronze_manifest_path).read_text(encoding="utf-8"))
    assert len(manifest["responses"]) == 3
    assert manifest["weather_reuse"][0]["original_collection_run_id"] == first.id
