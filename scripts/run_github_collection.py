"""One CI collection; secrets stay in env/temp CA, Bronze is uploaded by the workflow."""
import json
import os
from pathlib import Path
import tempfile

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

from ingestion.main import run
from shared.config import ROOT, Settings
from shared.database import make_engine
from shared.logging_config import configure_logging
from shared.time import utcnow


def station_ids():
    value = os.getenv("STATION_IDS", "").strip()
    if value:
        ids = [item.strip() for item in value.split(",")]
    else:
        data = json.loads((ROOT / "config" / "citibike_stations.json").read_text(encoding="utf-8"))
        if data.get("source") != "citibike":
            raise ValueError("Station configuration must use source=citibike")
        ids = data["station_ids"]
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 100
            or any(not isinstance(item, str) or not item or len(item) > 128 or "," in item for item in ids)
            or len(ids) != len(set(ids))):
        raise ValueError("Configure 1-100 unique string STATION_IDS")
    return tuple(ids)


def check_migration(settings):
    """Only inspect the ledger. CI never changes schema or stamps a database."""
    engine = make_engine(settings)
    try:
        with engine.connect() as connection:
            expected = set(ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_heads())
            actual = set(MigrationContext.configure(connection).get_current_heads())
            if actual != expected:
                raise ValueError("Database migration is not at head; run migrations manually first")
    finally:
        engine.dispose()


def main():
    bronze_dir = ROOT / "data" / "bronze"
    certificate_path = None
    summary = {"started_at_utc": utcnow().isoformat(), "collector_started": False,
               "github_run_id": os.getenv("GITHUB_RUN_ID"),
               "github_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT")}
    exit_code = 1
    try:
        # Prevent accidental use of a developer's .env inside a published checkout.
        if (ROOT / ".env").exists():
            raise ValueError("CI must use GitHub Secrets, not a checked-in .env")
        if os.getenv("GITHUB_ACTIONS") != "true":
            raise ValueError("This command is for GitHub Actions; use ingestion.main --once locally")
        required = ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_DATABASE", "MYSQL_USER",
                    "MYSQL_PASSWORD", "MYSQL_CA_CERT", "RUNNER_TEMP")
        missing = [name for name in required if not os.getenv(name, "").strip()]
        if missing:
            # Names are safe; do not print their values or underlying exceptions.
            print("Missing GitHub Secrets/environment: " + ", ".join(missing))
            raise ValueError("Incomplete CI configuration")
        selected = station_ids()
        os.environ["STATION_IDS"] = ",".join(selected)
        os.environ["DISPLAY_TIMEZONE"] = "America/New_York"
        os.environ["BIKE_SOURCE"] = "citibike"
        os.environ["BRONZE_DIR"] = str(bronze_dir)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".pem",
                                         prefix="citibike-ca-", dir=os.environ["RUNNER_TEMP"],
                                         delete=False) as certificate:
            certificate_path = Path(certificate.name)
            certificate.write(os.environ["MYSQL_CA_CERT"])
        certificate_path.chmod(0o600)
        os.environ["MYSQL_SSL_CA"] = str(certificate_path)
        settings = Settings.load()
        configure_logging(settings.display_timezone)
        check_migration(settings)
        print(f"Migration check: OK; collecting {len(selected)} stations once.")
        summary["station_count"] = len(selected)
        summary["collector_started"] = True
        exit_code = run(settings, schedule=False)
    except Exception as exc:
        # Database exceptions and CA parsing errors may contain private values.
        summary["error_type"] = type(exc).__name__
        print(f"GitHub collection failed ({type(exc).__name__}). Check Secrets, CA, migration and network access.")
    finally:
        if certificate_path is not None:
            certificate_path.unlink(missing_ok=True)
        summary["finished_at_utc"] = utcnow().isoformat()
        summary["exit_code"] = exit_code
        bronze_dir.mkdir(parents=True, exist_ok=True)
        # Uploaded with Bronze, so GitHub run ID maps back to the DB manifest path.
        summary["manifests"] = sorted(path.relative_to(bronze_dir).as_posix()
                                      for path in bronze_dir.glob("citibike/**/manifest.json"))
        (bronze_dir / "github_collection.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
