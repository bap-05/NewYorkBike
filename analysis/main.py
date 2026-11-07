"""Independent CLI: one analysis run, or an explicitly started five-minute loop."""
import argparse
from datetime import datetime, timedelta
import logging
import json
from pathlib import Path
import time
from sqlalchemy.orm import Session

from analysis.config import AnalysisOptions
from analysis.dataset import calculate_results, selected_stations
from analysis.statistics import period_start
from analysis.worker import analyze_once
from shared.config import Settings
from shared.database import make_engine, service_session
from shared.logging_config import configure_logging
from shared.time import as_utc, display_time, utcnow

logger = logging.getLogger("analysis")


def preview(settings, options, *, cutoff=None, output="artifacts/analysis_preview.json"):
    instant = period_start(as_utc(cutoff) if cutoff else utcnow(), 300)
    if instant > utcnow():
        raise ValueError("Analysis cutoff cannot be in the future")
    engine = make_engine(settings)
    try:
        with engine.connect() as connection:
            if engine.dialect.name == "mysql":
                connection.exec_driver_sql("SET SESSION TRANSACTION READ ONLY")
            with Session(bind=connection) as session:
                rows, summary = calculate_results(session, settings, options, instant)
                names = {s.station_id: s.name for s in selected_stations(session, settings)}
                # Preview is local only. No service markers or Gold writes.
                report = {"database_written": False, "summary": summary,
                    "configuration": options.as_dict(), "station_names": names, "results": rows}
                target = Path(output).resolve()
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(report, indent=2, ensure_ascii=True, default=str) + "\n", encoding="utf-8")
                logger.info("Analysis preview: input_rows=%s stations=%s metrics=%s output=%s",
                    summary["input_rows"], summary["station_count"], len(rows), target)
                logger.info("No database writes; quality_counts=%s", summary["quality_counts"])
        return 0
    finally:
        engine.dispose()


def run(settings, options, *, schedule=False, cutoff=None):
    engine = make_engine(settings)
    try:
        while True:
            code = 0
            try:
                with service_session(engine, "analysis") as session:
                    result = analyze_once(session, settings, options, cutoff=cutoff)
                    logger.info("analysis_run=%s cutoff=%s status=%s changed_metrics=%s attempts=%s",
                        result.id, display_time(result.scheduled_at), result.status, result.result_count, result.attempt_count)
                    logger.info("Analysis summary=%s", result.summary)
            except Exception as exc:
                logger.error("Analysis failed (%s). Check MySQL, migrations and service_runs.", type(exc).__name__)
                code = 1
            if not schedule:
                return code
            next_run = period_start(utcnow(), 300) + timedelta(minutes=5)
            logger.info("Next analysis=%s [America/New_York]", display_time(next_run))
            while (remaining := (next_run - utcnow()).total_seconds()) > 0:
                time.sleep(min(remaining, 30))
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Independent Citi Bike Gold analysis, no external API calls")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--preview", action="store_true", help="Read-only calculation; save a local JSON report, no migration needed")
    mode.add_argument("--schedule", action="store_true", help="Run now, then at five-minute wall-clock boundaries")
    parser.add_argument("--cutoff", help="Optional past ISO timestamp WITH offset; --once or --preview")
    parser.add_argument("--output", default="artifacts/analysis_preview.json", help="Local preview JSON path")
    args = parser.parse_args()
    if args.schedule and args.cutoff:
        parser.error("--cutoff is only valid with --once")
    configure_logging("America/New_York")
    try:
        settings = Settings.load(outbound=False)
        options = AnalysisOptions.load()
        cutoff = as_utc(datetime.fromisoformat(args.cutoff.replace("Z", "+00:00"))) if args.cutoff else None
        if args.preview:
            return preview(settings, options, cutoff=cutoff, output=args.output)
        return run(settings, options, schedule=args.schedule, cutoff=cutoff)
    except KeyboardInterrupt:
        logger.info("Analysis stopped")
        return 130
    except Exception as exc:
        logger.error("Analysis startup failed (%s). Check configuration and MySQL.", type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
