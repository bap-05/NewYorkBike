"""Add independent service bookkeeping and Gold statistics; never alter Silver."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

revision = "0004_analysis"
down_revision = "0003_bronze"
branch_labels = None
depends_on = None


def dt():
    return sa.DateTime().with_variant(DATETIME(fsp=6), "mysql")


def upgrade():
    options = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"}
    op.create_table("service_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("service_name", sa.String(32), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("scheduled_at", dt(), nullable=False),
        sa.Column("started_at", dt(), nullable=False),
        sa.Column("finished_at", dt()),
        sa.Column("heartbeat_at", dt(), nullable=False),
        sa.Column("input_watermark", dt()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt_count", sa.Integer, nullable=False),
        sa.Column("calculation_version", sa.String(32), nullable=False),
        sa.Column("configuration_hash", sa.String(64), nullable=False),
        sa.Column("configuration", sa.JSON, nullable=False),
        sa.Column("summary", sa.JSON),
        sa.Column("result_count", sa.Integer, nullable=False),
        sa.Column("error_summary", sa.String(255)),
        sa.UniqueConstraint("source", "id", name="uq_service_source_id"),
        sa.UniqueConstraint("service_name", "source", "scheduled_at", "calculation_version", "configuration_hash", name="uq_service_period_config"),
        sa.CheckConstraint("status IN ('running','success','skipped','failed')", name="ck_service_status"),
        sa.CheckConstraint("attempt_count >= 1 AND result_count >= 0", name="ck_service_counts"), **options)
    op.create_index("ix_service_latest", "service_runs", ["service_name", "source", "scheduled_at"])
    op.create_table("analysis_results",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("station_id", sa.String(128), nullable=False),
        sa.Column("window_start", dt(), nullable=False),
        sa.Column("window_end", dt(), nullable=False),
        sa.Column("aggregation", sa.String(16), nullable=False),
        sa.Column("metric_name", sa.String(64), nullable=False),
        sa.Column("metric_value", sa.Double),
        sa.Column("sample_count", sa.Integer, nullable=False),
        sa.Column("observed_sample_count", sa.Integer, nullable=False),
        sa.Column("expected_sample_count", sa.Integer, nullable=False),
        sa.Column("coverage", sa.Double),
        sa.Column("quality_status", sa.String(24), nullable=False),
        sa.Column("dimensions", sa.JSON, nullable=False),
        sa.Column("input_cutoff", dt(), nullable=False),
        sa.Column("input_watermark", dt()),
        sa.Column("calculated_at", dt(), nullable=False),
        sa.Column("calculation_version", sa.String(32), nullable=False),
        sa.Column("configuration_hash", sa.String(64), nullable=False),
        sa.Column("service_run_id", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(["source", "station_id"], ["stations.source", "stations.station_id"], name="fk_analysis_station", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source", "service_run_id"], ["service_runs.source", "service_runs.id"], name="fk_analysis_service", ondelete="RESTRICT"),
        sa.UniqueConstraint("source", "station_id", "window_start", "window_end", "aggregation", "metric_name", "calculation_version", "configuration_hash", name="uq_analysis_window_metric"),
        sa.CheckConstraint("window_end > window_start", name="ck_analysis_window"),
        sa.CheckConstraint("aggregation IN ('hour','day')", name="ck_analysis_aggregation"),
        sa.CheckConstraint("sample_count >= 0 AND observed_sample_count >= 0 AND expected_sample_count >= 0", name="ck_analysis_counts"),
        sa.CheckConstraint("coverage IS NULL OR (coverage >= 0 AND coverage <= 1)", name="ck_analysis_coverage"),
        sa.CheckConstraint("quality_status IN ('ok','low_coverage','insufficient_data')", name="ck_analysis_quality"), **options)
    op.create_index("ix_analysis_station_window", "analysis_results", ["source", "station_id", "window_start"])


def downgrade():
    raise RuntimeError("Forward-only: retain published analysis and service history")
