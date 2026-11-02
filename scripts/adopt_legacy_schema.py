"""Validate an unversioned schema before recording its legacy baseline; no data changes."""
import argparse
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from shared.config import Settings, ROOT
from shared.database import make_engine


def main():
    parser = argparse.ArgumentParser(description="Inspect manual legacy schema, optionally record baseline")
    parser.add_argument("--stamp", action="store_true", help="Record 0001 after checks; does not run schema creation")
    args = parser.parse_args()
    engine = make_engine(Settings.load())
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            tables = set(inspector.get_table_names())
            if "alembic_version" in tables:
                raise ValueError("alembic_version already exists; use alembic current instead")
            required = {
                "stations": {"station_id", "name", "latitude", "longitude", "rack_count", "is_monitored", "updated_at"},
                "collection_runs": {"id", "scheduled_at", "started_at", "finished_at", "source", "status", "success_count", "error_count", "error_summary"},
                "bike_observations": {"id", "station_id", "collection_run_id", "sampled_at", "collected_at", "source_observed_at", "available_bikes", "quality_status"},
                "weather_observations": {"id", "source", "requested_latitude", "requested_longitude", "weather_time", "collected_at", "interval_seconds", "temperature", "humidity", "rain", "wind_speed"},
                "observation_weather_links": {"bike_observation_id", "weather_observation_id"},
            }
            if not set(required) <= tables:
                raise ValueError("Missing legacy tables; do not stamp this database")
            for table, expected in required.items():
                names = {c["name"] for c in inspector.get_columns(table)}
                if not expected <= names:
                    raise ValueError("Legacy schema missing required columns; manual review needed")
                if "source" in names and table in ("stations", "bike_observations"):
                    raise ValueError("Schema already has source identity; review migration state")
                if table == "weather_observations" and "units" not in names and not {
                    "temperature_unit", "humidity_unit", "rain_unit", "wind_speed_unit"} <= names:
                    raise ValueError("Weather units are not identifiable; do not stamp")
                print(table, "rows=", connection.scalar(text("SELECT COUNT(*) FROM `" + table + "`")))
            if inspector.get_pk_constraint("stations")["constrained_columns"] != ["station_id"]:
                raise ValueError("Unexpected legacy station primary key")
            for table in tables:
                for fk in inspector.get_foreign_keys(table):
                    if fk["referred_table"] == "stations" and table != "bike_observations":
                        raise ValueError("Additional station references need a reviewed migration")
            print("Legacy schema recognized; 0002 will preserve legacy columns and values.")
        if args.stamp:
            command.stamp(Config(str(ROOT / "alembic.ini")), "0001_ingestion")
            print("Recorded baseline 0001_ingestion; run alembic upgrade head next.")
    except Exception as exc:
        # No raw driver exceptions or configuration values in output.
        print("Adoption failed:", str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
