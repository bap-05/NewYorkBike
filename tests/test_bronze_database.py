from datetime import UTC, datetime, timedelta
import gzip

import httpx
from sqlalchemy import create_engine, select

from ingestion.bronze import DatabaseBronzeArchive, bronze_entries


def test_database_capture_and_seven_day_retention(monkeypatch):
    now = datetime(2026, 11, 25, 12, tzinfo=UTC)
    engine = create_engine("sqlite://")
    bronze_entries.metadata.create_all(engine)
    archive = DatabaseBronzeArchive(engine)
    monkeypatch.setattr("ingestion.bronze.utcnow", lambda: now)
    path = archive.begin(run_id=1, attempt_count=1, scheduled_at=now,
                         source="citibike", station_ids=["test"])
    archive.record_response(httpx.Response(200, content=b'{"data": []}'),
                            source="citibike", request_attempt=1, url="https://example.com/test")
    archive.finish("complete", planned_silver_status="success")

    with engine.connect() as connection:
        rows = {row.archive_path: row for row in connection.execute(select(bronze_entries))}
    manifest = rows[path.removeprefix("mysql:")].manifest
    body_path = path.removeprefix("mysql:").rsplit("/", 1)[0] + "/" + manifest["responses"][0]["body_file"]
    assert manifest["capture_status"] == "complete"
    assert gzip.decompress(rows[body_path].compressed_body) == b'{"data": []}'
    assert archive.purge_expired(now + timedelta(days=7, seconds=-1)) == 0
    assert archive.purge_expired(now + timedelta(days=7)) == 2
    engine.dispose()
