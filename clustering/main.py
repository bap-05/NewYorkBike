"""Independent CLI: read-only preview, single publication, or daily NY schedule."""
import argparse
from datetime import datetime, time as day_time, timedelta
import json
import logging
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from clustering.config import ClusteringOptions
from clustering.worker import calculate, cluster_once
from shared.config import Settings
from shared.database import make_engine, service_session
from shared.logging_config import configure_logging
from shared.time import UTC, as_utc, display_time, utcnow

logger = logging.getLogger("clustering")


def next_daily_run(instant):
    """02:00 NY daily; a missing spring 02:00 advances to 03:00, never +86400s."""
    instant = as_utc(instant)
    zone = ZoneInfo("America/New_York")
    date = instant.astimezone(zone).date()
    while True:
        target = datetime.combine(date, day_time(2), zone).astimezone(UTC)
        if target > instant:
            return target
        date += timedelta(days=1)


def preview(settings, options, *, cutoff=None, output="artifacts/clustering_preview.json"):
    instant = as_utc(cutoff) if cutoff is not None else utcnow()
    if instant > utcnow():
        raise ValueError("Clustering cutoff cannot be in the future")
    engine = make_engine(settings)
    try:
        with engine.connect() as connection:
            if engine.dialect.name == "mysql":
                connection.exec_driver_sql("SET SESSION TRANSACTION READ ONLY")
            with Session(bind=connection) as session:
                members, parameters, summary = calculate(session, settings, options, instant)
                report = {"database_written": False, "configuration": options.as_dict(),
                    "parameters": parameters, "summary": summary, "members": members}
                target = Path(output).resolve()
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(report, indent=2, ensure_ascii=True, default=str) + "\n", encoding="utf-8")
                logger.info("Clustering preview: status=%s input_rows=%s eligible=%s/%s members=%s output=%s",
                    parameters["status"], summary["input_rows"], summary["eligible_stations"],
                    summary["station_count"], len(members), target)
                logger.info("No database writes; reason=%s", parameters.get("reason"))
        return 0
    finally:
        engine.dispose()


def run(settings, options, *, schedule=False, cutoff=None):
    engine = make_engine(settings)
    try:
        while True:
            code = 0
            try:
                with service_session(engine, "clustering") as session:
                    result = cluster_once(session, settings, options, cutoff=cutoff)
                    logger.info("clustering_run=%s run_date=%s status=%s eligible=%s groups=%s reason=%s",
                        result.id, result.run_date, result.status, result.summary["eligible_stations"],
                        result.parameters.get("selected_k"), result.parameters.get("reason"))
            except Exception as exc:
                logger.error("Clustering failed (%s). Check migration 0005_clustering and service_runs.", type(exc).__name__)
                code = 1
            if not schedule:
                return code
            target = next_daily_run(utcnow())
            logger.info("Next clustering=%s [America/New_York]", display_time(target))
            while (remaining := (target - utcnow()).total_seconds()) > 0:
                time.sleep(min(remaining, 30))
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Independent daily station clustering from completed Silver")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true", help="Read-only report; no new migration required")
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--schedule", action="store_true", help="Run now, then daily at 02:00 America/New_York")
    parser.add_argument("--cutoff", help="Past ISO timestamp WITH UTC offset, defines logical NY run date")
    parser.add_argument("--output", default="artifacts/clustering_preview.json")
    args = parser.parse_args()
    if args.cutoff and args.schedule:
        parser.error("--cutoff is only valid with --once or --preview")
    configure_logging("America/New_York")
    try:
        settings, options = Settings.load(outbound=False), ClusteringOptions.load()
        cutoff = as_utc(datetime.fromisoformat(args.cutoff.replace("Z", "+00:00"))) if args.cutoff else None
        if args.preview:
            return preview(settings, options, cutoff=cutoff, output=args.output)
        from shared.schema import check_schema
        from shared.models import ClusteringRun, ServiceRun, StationCluster
        check_schema(settings, required_revision="0005_clustering", models=(ServiceRun, ClusteringRun, StationCluster))
        return run(settings, options, schedule=args.schedule, cutoff=cutoff)
    except KeyboardInterrupt:
        logger.info("Clustering stopped")
        return 130
    except Exception as exc:
        logger.error("Clustering startup failed (%s). Check configuration, dependencies and MySQL.", type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
