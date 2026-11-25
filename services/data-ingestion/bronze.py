"""Append-only response bodies and an atomic manifest for each collection attempt."""
from contextlib import suppress
from datetime import timedelta
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy import Column, DateTime, JSON, LargeBinary, MetaData, String, Table
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.exc import SQLAlchemyError

from shared.time import as_utc, utcnow


class BronzeError(RuntimeError):
    """Safe to report without leaking HTTP URLs, proxy credentials or payloads."""


def _public_request(url, params):
    parsed = urlsplit(str(url))
    # Credentials, query tokens and fragments are deliberately excluded from metadata.
    host = parsed.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    if parsed.port:
        host += f":{parsed.port}"
    metadata = {"url": urlunsplit((parsed.scheme, host, parsed.path, "", ""))}
    coordinates = {}
    for name in ("latitude", "longitude"):
        if params and name in params:
            try:
                value = float(params[name])
                if math.isfinite(value):
                    coordinates[name] = value
            except (ValueError, TypeError):
                pass
    if coordinates:
        metadata["coordinates"] = coordinates
    return metadata


class BronzeArchive:
    """Files survive Silver rollbacks. Database run status remains publication authority."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self._manifest = None
        self._directory = None
        self.active = False

    @property
    def manifest_path(self):
        if self._directory is None:
            return None
        return (self._directory / "manifest.json").relative_to(self.root).as_posix()

    def begin(self, *, run_id, attempt_count, scheduled_at, source, station_ids):
        if self.active:
            raise BronzeError("Bronze attempt is already open")
        if source != "citibike" or run_id < 1 or attempt_count < 1:
            raise BronzeError("Invalid Bronze attempt context")
        scheduled_at = as_utc(scheduled_at)
        self._directory = (self.root / source / scheduled_at.strftime("%Y/%m/%d") /
                           f"run_{run_id}" / f"attempt_{attempt_count}_{uuid4().hex}")
        self._manifest = {
            "format_version": "bronze-v1", "layer": "bronze", "source": source,
            "collection_run_id": run_id, "collection_attempt": attempt_count,
            "scheduled_at": scheduled_at.isoformat(), "started_at": utcnow().isoformat(),
            "station_ids": list(station_ids), "capture_status": "collecting",
            "responses": [], "network_failures": [], "weather_reuse": [],
        }
        try:
            self._prepare_attempt()
            self._save_manifest()
        except OSError:
            raise BronzeError("Cannot create Bronze archive; check storage path, permissions and disk space") from None
        self.active = True
        return self.manifest_path

    def _prepare_attempt(self):
        self._directory.mkdir(parents=True, exist_ok=False)

    def _save_body(self, filename, body):
        with (self._directory / filename).open("xb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())

    def _save_manifest(self):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", prefix=".manifest_", suffix=".tmp",
                                             dir=self._directory, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(json.dumps(self._manifest, ensure_ascii=False, indent=2).encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._directory / "manifest.json")
        finally:
            if temporary is not None:
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)

    def record_response(self, response, *, source, request_attempt, url, params=None):
        if not self.active:
            raise BronzeError("HTTP response has no active Bronze collection attempt")
        received_at = utcnow().isoformat()
        body = response.content  # Exact HTTPX decoded bytes, never json.dumps(parsed_payload).
        metadata = {
            "response_id": uuid4().hex, "source": source, "request_attempt": request_attempt,
            "received_at": received_at, "http_status": response.status_code,
            "content_type": response.headers.get("content-type", "").split(";", 1)[0],
            **_public_request(url, params),
        }
        try:
            if response.status_code == 407:
                # A proxy auth error is not source data and can echo proxy account details.
                metadata["body_omitted"] = "proxy_authentication_error"
            else:
                filename = f"response_{len(self._manifest['responses']) + 1:04d}_{metadata['response_id']}.body"
                # Exclusive creation: never overwrite a previous response, even on retry.
                self._save_body(filename, body)
                metadata.update(body_file=filename, size_bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
            self._manifest["responses"].append(metadata)
            self._save_manifest()
        except OSError:
            raise BronzeError("Cannot persist Bronze response; Silver writes must stop") from None

    def record_failure(self, *, source, request_attempt, error_type, url, params=None):
        if not self.active:
            raise BronzeError("Network request has no active Bronze collection attempt")
        self._manifest["network_failures"].append({
            "source": source, "request_attempt": request_attempt, "error_type": error_type,
            "received_at": utcnow().isoformat(), **_public_request(url, params),
        })
        try:
            self._save_manifest()
        except OSError:
            raise BronzeError("Cannot persist Bronze network failure") from None

    def record_weather_reuse(self, *, station_id, weather_observation_id, original_run_id, reason):
        if not self.active:
            raise BronzeError("Weather reuse has no active Bronze collection attempt")
        self._manifest["weather_reuse"].append({
            "station_id": station_id, "weather_observation_id": weather_observation_id,
            "original_collection_run_id": original_run_id, "reason": reason,
        })
        try:
            self._save_manifest()
        except OSError:
            raise BronzeError("Cannot persist Bronze weather provenance") from None

    def finish(self, capture_status, *, planned_silver_status=None):
        if not self.active:
            return
        self._manifest["capture_status"] = capture_status
        self._manifest["finished_at"] = utcnow().isoformat()
        self._manifest["planned_silver_status"] = planned_silver_status
        try:
            self._save_manifest()
        except OSError:
            raise BronzeError("Cannot finalize Bronze manifest; Silver writes must stop") from None
        self.active = False

    def reset(self):
        if self.active:
            with suppress(BronzeError):
                self.finish("aborted")
        self.active = False


bronze_entries = Table(
    "du_lieu_tho_bronze", MetaData(),
    Column("archive_path", String(255), primary_key=True),
    Column("stored_at", DateTime, nullable=False, index=True),
    Column("manifest", JSON),
    Column("compressed_body", LargeBinary().with_variant(LONGBLOB(), "mysql")),
)


class DatabaseBronzeArchive(BronzeArchive):
    """Persist captures independently of the Silver transaction."""

    def __init__(self, engine):
        super().__init__(Path.cwd())
        self.engine = engine

    @property
    def manifest_path(self):
        path = super().manifest_path
        return f"mysql:{path}" if path is not None else None

    def _prepare_attempt(self):
        self._insert(super().manifest_path, manifest=self._manifest)

    def _save_manifest(self):
        try:
            with self.engine.begin() as connection:
                connection.execute(bronze_entries.update().where(
                    bronze_entries.c.archive_path == super().manifest_path
                ).values(manifest=self._manifest))
        except SQLAlchemyError:
            raise OSError("Cannot update Bronze manifest") from None

    def _save_body(self, filename, body):
        path = self._directory.relative_to(self.root) / filename
        self._insert(path.as_posix(), compressed_body=gzip.compress(body, compresslevel=3))

    def _insert(self, path, **values):
        try:
            with self.engine.begin() as connection:
                connection.execute(bronze_entries.insert().values(
                    archive_path=path, stored_at=utcnow().replace(tzinfo=None), **values))
        except SQLAlchemyError:
            raise OSError("Cannot insert Bronze entry") from None

    def purge_expired(self, now):
        cutoff = (as_utc(now) - timedelta(days=7)).replace(tzinfo=None)
        with self.engine.begin() as connection:
            result = connection.execute(bronze_entries.delete().where(
                bronze_entries.c.stored_at <= cutoff))
            return result.rowcount


class RecordingClient:
    """Keep transport/proxy behavior; get_json records before parsing or validation."""

    def __init__(self, client, bronze):
        self.client, self.bronze = client, bronze

    def get(self, url, *, params=None):
        return self.client.get(url, params=params)
