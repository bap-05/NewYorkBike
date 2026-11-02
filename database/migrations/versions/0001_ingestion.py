"""Initial ingestion schema, no seed data. MySQL 8.0.16+."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

revision = "0001_ingestion"
down_revision = None
branch_labels = None
depends_on = None


def dt():
    return sa.DateTime().with_variant(DATETIME(fsp=6), "mysql")


def upgrade():
    options = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"}
    op.create_table("stations",
        sa.Column("station_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("latitude", sa.Numeric(10, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(10, 6), nullable=False),
        sa.Column("rack_count", sa.Integer),
        sa.Column("is_monitored", sa.Boolean, nullable=False),
        sa.Column("updated_at", dt(), nullable=False),
        sa.CheckConstraint("rack_count IS NULL OR rack_count >= 0", name="ck_station_racks"),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_station_latitude"),
        sa.CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_station_longitude"), **options)
    op.create_table("collection_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("scheduled_at", dt(), nullable=False, unique=True),
        sa.Column("started_at", dt(), nullable=False),
        sa.Column("finished_at", dt()),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("success_count", sa.Integer, nullable=False),
        sa.Column("error_count", sa.Integer, nullable=False),
        sa.Column("attempt_count", sa.Integer, nullable=False),
        sa.Column("error_summary", sa.Text),
        sa.CheckConstraint("status IN ('running','success','partial','failed')", name="ck_run_status"), **options)
    op.create_table("bike_observations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("station_id", sa.String(64), sa.ForeignKey("stations.station_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("collection_run_id", sa.Integer, sa.ForeignKey("collection_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sampled_at", dt(), nullable=False),
        sa.Column("collected_at", dt(), nullable=False),
        sa.Column("source_observed_at", dt()),
        sa.Column("available_bikes", sa.Integer),
        sa.Column("quality_status", sa.String(32), nullable=False),
        sa.UniqueConstraint("station_id", "sampled_at", name="uq_bike_station_sample"),
        sa.CheckConstraint("available_bikes IS NULL OR available_bikes >= 0", name="ck_bike_count"),
        sa.CheckConstraint("quality_status IN ('valid','missing','invalid')", name="ck_bike_quality"), **options)
    op.create_index("ix_bike_station_collected", "bike_observations", ["station_id", "collected_at"])
    op.create_index("ix_bike_run", "bike_observations", ["collection_run_id"])
    op.create_table("weather_observations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("requested_latitude", sa.Numeric(10, 6), nullable=False),
        sa.Column("requested_longitude", sa.Numeric(10, 6), nullable=False),
        sa.Column("returned_latitude", sa.Numeric(10, 6)),
        sa.Column("returned_longitude", sa.Numeric(10, 6)),
        sa.Column("weather_time", dt(), nullable=False),
        sa.Column("collected_at", dt(), nullable=False),
        sa.Column("temperature", sa.Float),
        sa.Column("humidity", sa.Float),
        sa.Column("rain", sa.Float),
        sa.Column("wind_speed", sa.Float),
        sa.Column("units", sa.JSON, nullable=False),
        sa.Column("interval_seconds", sa.Integer, nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.UniqueConstraint("requested_latitude", "requested_longitude", "weather_time", "source", name="uq_weather_location_time_source"),
        sa.CheckConstraint("humidity IS NULL OR humidity BETWEEN 0 AND 100", name="ck_weather_humidity"),
        sa.CheckConstraint("rain IS NULL OR rain >= 0", name="ck_weather_rain"),
        sa.CheckConstraint("wind_speed IS NULL OR wind_speed >= 0", name="ck_weather_wind"),
        sa.CheckConstraint("interval_seconds > 0", name="ck_weather_interval"), **options)
    op.create_table("observation_weather_links",
        sa.Column("bike_observation_id", sa.Integer, sa.ForeignKey("bike_observations.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("weather_observation_id", sa.Integer, sa.ForeignKey("weather_observations.id", ondelete="RESTRICT"), nullable=False), **options)
    op.create_index("ix_observation_weather_links_weather_observation_id", "observation_weather_links", ["weather_observation_id"])


def downgrade():
    # Destructive: explicitly invoked by the operator, never by application startup.
    for table in ("observation_weather_links", "weather_observations", "bike_observations", "collection_runs", "stations"):
        op.drop_table(table)
