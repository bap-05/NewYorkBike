"""Add source isolation and GBFS fields without removing legacy data/columns.

Supports original 0001 and the inspected manual MySQL schema. Online MySQL only:
reflection is required to retain legacy constraint names, widths and extra columns.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

revision = "0002_citibike"
down_revision = "0001_ingestion"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name != "mysql":
        raise RuntimeError("0002 requires online MySQL schema inspection")
    inspector = sa.inspect(connection)
    columns = {table: {c["name"]: c for c in inspector.get_columns(table)} for table in (
        "stations", "collection_runs", "bike_observations", "weather_observations")}
    # Fail before changing anything if other services already reference the old single-column key.
    for table in inspector.get_table_names():
        for fk in inspector.get_foreign_keys(table):
            if fk["referred_table"] == "stations" and table != "bike_observations":
                raise RuntimeError("Additional station foreign keys require a reviewed migration before 0002")
    duplicate_runs = connection.execute(sa.text(
        "SELECT 1 FROM collection_runs GROUP BY source, scheduled_at HAVING COUNT(*) > 1 LIMIT 1")).first()
    if duplicate_runs:
        raise RuntimeError("Duplicate legacy runs require review; no records were removed")
    duplicate_weather = connection.execute(sa.text("""SELECT 1 FROM weather_observations
        GROUP BY requested_latitude, requested_longitude, weather_time, source
        HAVING COUNT(*) > 1 LIMIT 1""")).first()
    if duplicate_weather:
        raise RuntimeError("Legacy weather duplicates need review; no records were removed")

    def add(table, column):
        if column.name not in columns[table]:
            op.add_column(table, column)

    for table in ("stations", "bike_observations"):
        add(table, sa.Column("source", sa.String(32), nullable=False, server_default="seoul"))
    add("stations", sa.Column("capacity", sa.Integer, nullable=True))
    add("stations", sa.Column("information_updated_at", DATETIME(fsp=6), nullable=True))
    add("collection_runs", sa.Column("attempt_count", sa.Integer, nullable=False, server_default="1"))
    add("collection_runs", sa.Column("feed_metadata", sa.JSON, nullable=True))
    # Widen enum to string: retain every historical source/status value.
    for column, width in (("source", 64), ("status", 16)):
        op.alter_column("collection_runs", column, existing_type=columns["collection_runs"][column]["type"],
                        type_=sa.String(width), existing_nullable=False)
    for column in (sa.Column("available_docks", sa.Integer, nullable=True),
                   sa.Column("is_installed", sa.Boolean, nullable=True),
                   sa.Column("is_renting", sa.Boolean, nullable=True),
                   sa.Column("is_returning", sa.Boolean, nullable=True),
                   sa.Column("feed_last_updated", DATETIME(fsp=6), nullable=True),
                   sa.Column("gbfs_version", sa.String(8), nullable=True)):
        add("bike_observations", column)
    op.alter_column("bike_observations", "available_bikes", existing_type=sa.Integer, nullable=True)
    op.alter_column("bike_observations", "quality_status", existing_type=columns["bike_observations"]["quality_status"]["type"],
                    type_=sa.String(32), existing_nullable=False)
    checks = {c["name"] for c in inspector.get_check_constraints("bike_observations")}
    if "ck_bike_quality" in checks:
        op.drop_constraint("ck_bike_quality", "bike_observations", type_="check")
    op.create_check_constraint("ck_bike_quality", "bike_observations",
                               "quality_status IN ('valid','missing','invalid','inactive','stale')")
    if "ck_bike_docks" not in checks:
        op.create_check_constraint("ck_bike_docks", "bike_observations", "available_docks IS NULL OR available_docks >= 0")
    if "ck_station_capacity" not in {c["name"] for c in inspector.get_check_constraints("stations")}:
        op.create_check_constraint("ck_station_capacity", "stations", "capacity IS NULL OR capacity >= 0")
    # Replace only relationships/indexes; never drop or rename a table/column.
    for fk in inspector.get_foreign_keys("bike_observations"):
        if fk["referred_table"] == "stations":
            op.drop_constraint(fk["name"], "bike_observations", type_="foreignkey")
    for unique in inspector.get_unique_constraints("bike_observations"):
        if unique["column_names"] == ["station_id", "sampled_at"]:
            op.drop_index(unique["name"], table_name="bike_observations")
    # Widen IDs; preserve all raw IDs and historical rack_count values.
    for table in ("stations", "bike_observations"):
        op.alter_column(table, "station_id", existing_type=columns[table]["station_id"]["type"],
                        type_=sa.String(128), existing_nullable=False)
    if inspector.get_pk_constraint("stations")["constrained_columns"] != ["source", "station_id"]:
        # Managed MySQL can require a primary key at all times. Replace it in
        # one ALTER instead of leaving a keyless table between two statements.
        op.execute(sa.text("ALTER TABLE `stations` DROP PRIMARY KEY, ADD PRIMARY KEY (`source`, `station_id`)"))
    op.create_foreign_key("fk_bike_source_station", "bike_observations", "stations",
                          ["source", "station_id"], ["source", "station_id"], ondelete="RESTRICT")
    if "uq_bike_source_station_sample" not in {u["name"] for u in inspector.get_unique_constraints("bike_observations")}:
        op.create_unique_constraint("uq_bike_source_station_sample", "bike_observations", ["source", "station_id", "sampled_at"])
    if "ix_bike_source_station_time" not in {i["name"] for i in inspector.get_indexes("bike_observations")}:
        op.create_index("ix_bike_source_station_time", "bike_observations", ["source", "station_id", "collected_at"])
    for unique in inspector.get_unique_constraints("collection_runs"):
        if unique["column_names"] == ["scheduled_at"]:
            op.drop_index(unique["name"], table_name="collection_runs")
    if "uq_run_source_sample" not in {u["name"] for u in inspector.get_unique_constraints("collection_runs")}:
        op.create_unique_constraint("uq_run_source_sample", "collection_runs", ["source", "scheduled_at"])

    # Manual schema stores weather units in separate columns. Keep those values and
    # their original wind units; adding JSON must not relabel old km/h values as m/s.
    add("weather_observations", sa.Column("units", sa.JSON, nullable=True))
    had_unit_columns = all(name in columns["weather_observations"] for name in (
        "temperature_unit", "humidity_unit", "rain_unit", "wind_speed_unit"))
    for name in ("temperature_unit", "humidity_unit", "rain_unit", "wind_speed_unit"):
        add("weather_observations", sa.Column(name, sa.String(20), nullable=True))
    if had_unit_columns:
        op.execute(sa.text("""UPDATE weather_observations SET units = JSON_OBJECT(
            'temperature_2m',temperature_unit,'relative_humidity_2m',humidity_unit,
            'rain',rain_unit,'wind_speed_10m',wind_speed_unit) WHERE units IS NULL"""))
    else:
        op.execute(sa.text("""UPDATE weather_observations SET
            temperature_unit=JSON_UNQUOTE(JSON_EXTRACT(units,'$.temperature_2m')),
            humidity_unit=JSON_UNQUOTE(JSON_EXTRACT(units,'$.relative_humidity_2m')),
            rain_unit=JSON_UNQUOTE(JSON_EXTRACT(units,'$.rain')),
            wind_speed_unit=JSON_UNQUOTE(JSON_EXTRACT(units,'$.wind_speed_10m'))"""))
    op.alter_column("weather_observations", "units", existing_type=sa.JSON, nullable=False)
    add("weather_observations", sa.Column("collection_run_id", sa.Integer, nullable=True))
    if "collection_run_id" in columns["weather_observations"]:
        op.alter_column("weather_observations", "collection_run_id",
            existing_type=columns["weather_observations"]["collection_run_id"]["type"], nullable=True)
    if not any(fk["constrained_columns"] == ["collection_run_id"] and fk["referred_table"] == "collection_runs"
               for fk in inspector.get_foreign_keys("weather_observations")):
        op.create_foreign_key("fk_weather_collection_run", "weather_observations", "collection_runs",
                              ["collection_run_id"], ["id"], ondelete="RESTRICT")
    # The manual unique index includes interval. Preserve it and add the canonical
    # source/location/time key only when old records already satisfy it.
    keys = {tuple(u["column_names"]) for u in inspector.get_unique_constraints("weather_observations")}
    canonical = ("requested_latitude", "requested_longitude", "weather_time", "source")
    if canonical not in keys:
        duplicate_weather = connection.execute(sa.text("""SELECT 1 FROM weather_observations
            GROUP BY requested_latitude, requested_longitude, weather_time, source
            HAVING COUNT(*) > 1 LIMIT 1""")).first()
        if duplicate_weather:
            raise RuntimeError("Legacy weather duplicates need review; all rows retained, migration partially applied")
        op.create_unique_constraint("uq_weather_location_time_source", "weather_observations", list(canonical))


def downgrade():
    raise RuntimeError("Forward-only migration: removing source identity would risk collisions and data loss")
