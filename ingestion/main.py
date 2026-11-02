"""CLI: explicitly choose discovery, one run, or the optional independent scheduler."""
import argparse
import json
import logging
import time

from sqlalchemy.exc import SQLAlchemyError

from ingestion.clients.http import SourceError
from ingestion.clients.proxy import OutboundClient
from ingestion.clients.citibike_client import CitiBikeClient
from ingestion.clients.weather_client import WeatherClient
from ingestion.collector import collect_once
from ingestion.bronze import BronzeArchive, RecordingClient
from shared.config import Settings
from shared.presentation import APP_NAME
from shared.database import ingestion_session, make_engine
from shared.logging_config import configure_logging
from shared.time import collection_instant, display_time, next_half_hour, utcnow

logger = logging.getLogger("ingestion")


def list_stations(citibike, limit=10, timezone_name="America/New_York"):
    """Live discovery only; does not require or write a database."""
    count = 0
    for station in citibike.fetch():
        # Initial selection: central Manhattan, strictly east of the Hudson/Jersey City.
        if (station.quality_status != "valid" or not station.is_returning
                or not 40.70 <= station.latitude <= 40.80 or not -74.015 <= station.longitude <= -73.95):
            continue
        print(json.dumps({"station_id": station.station_id, "name": station.name,
                          "latitude": str(station.latitude), "longitude": str(station.longitude),
                          "capacity": station.capacity, "available_bikes": station.available_bikes,
                          "source_observed_at": station.source_observed_at.isoformat(),
                          "source_observed_at_local": display_time(station.source_observed_at, timezone_name),
                          "display_timezone": timezone_name}, ensure_ascii=False))
        count += 1
        if count >= limit:
            break


def run(settings, *, list_only=False, schedule=False, limit=10):
    logger.info("Outbound routing: %s; routes=%s",
                "proxy" if settings.proxy_enabled else "direct",
                len(settings.proxy_urls) if settings.proxy_enabled else 1)
    logger.info("Display timezone=%s", settings.display_timezone)
    with OutboundClient(settings) as client:
        if list_only:
            list_stations(CitiBikeClient(client, settings), limit, settings.display_timezone)
            return 0
        if not settings.station_ids:
            raise ValueError("Fill STATION_IDS using real IDs from --list-stations")
        engine = make_engine(settings)
        bronze = BronzeArchive(settings.bronze_dir)
        recorded_client = RecordingClient(client, bronze)
        citibike, weather = CitiBikeClient(recorded_client, settings), WeatherClient(recorded_client, settings)
        try:
            slot = collection_instant(utcnow())
            while True:
                try:
                    with ingestion_session(engine) as session:
                        result = collect_once(session, citibike, weather, settings.station_ids,
                                              scheduled_at=slot, bronze=bronze)
                        logger.info("run=%s sample_time=%s status=%s valid_bikes=%s errors=%s attempts=%s",
                                    result.id, display_time(result.scheduled_at, settings.display_timezone), result.status,
                                    result.success_count, result.error_count, result.attempt_count)
                        if result.error_summary:
                            logger.warning("%s", result.error_summary)
                        logger.info("Bronze manifest=%s", result.bronze_manifest_path or "legacy (not captured)")
                        exit_code = 0 if result.status == "success" else 1
                except (SQLAlchemyError, RuntimeError, ValueError) as exc:
                    # Do not print DB/HTTP exceptions containing connection URLs or credentials.
                    logger.error("Collection failed (%s). Check Bronze storage, MySQL, migrations and collection_runs.", type(exc).__name__)
                    exit_code = 1
                if not schedule:
                    return exit_code
                # Schedule by wall-clock boundaries, not 30 minutes after the last run.
                # A boundary passed while collecting is skipped; never run in parallel.
                slot = next_half_hour(utcnow(), settings.display_timezone)
                logger.info("Next collection=%s [%s]", display_time(slot, settings.display_timezone), settings.display_timezone)
                while (remaining := (slot - utcnow()).total_seconds()) > 0:
                    time.sleep(min(remaining, 30))
        finally:
            engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=f"{APP_NAME} ingestion (independent from FastAPI)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list-stations", action="store_true", help="List live station IDs without DB writes")
    mode.add_argument("--once", action="store_true", help="Collect once at the current time")
    mode.add_argument("--schedule", action="store_true", help="Collect now, then at :00 and :30 in the display timezone (New York by default)")
    parser.add_argument("--limit", type=int, choices=range(1, 101), default=10, help="Number of active Manhattan stations to list")
    args = parser.parse_args()
    configure_logging()
    try:
        settings = Settings.load()
        if settings.display_timezone != "America/New_York":
            configure_logging(settings.display_timezone)
        return run(settings, list_only=args.list_stations, schedule=args.schedule, limit=args.limit)
    except (ValueError, SourceError) as exc:
        logger.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        logger.info("Ingestion stopped")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
