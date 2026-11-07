"""Add immutable daily clustering snapshots; retain all Silver and Analysis data."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

revision = "0005_clustering"
down_revision = "0004_analysis"
branch_labels = None
depends_on = None


def dt():
    return sa.DateTime().with_variant(DATETIME(fsp=6), "mysql")


def upgrade():
    options = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"}
    op.create_table("clustering_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("run_date", sa.Date, nullable=False),
        sa.Column("service_run_id", sa.Integer, nullable=False),
        sa.Column("window_start", dt(), nullable=False),
        sa.Column("window_end", dt(), nullable=False),
        sa.Column("input_cutoff", dt(), nullable=False),
        sa.Column("started_at", dt(), nullable=False),
        sa.Column("finished_at", dt()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("algorithm", sa.String(64), nullable=False),
        sa.Column("calculation_version", sa.String(32), nullable=False),
        sa.Column("configuration_hash", sa.String(64), nullable=False),
        sa.Column("feature_config", sa.JSON, nullable=False),
        sa.Column("parameters", sa.JSON),
        sa.Column("summary", sa.JSON),
        sa.UniqueConstraint("source", "id", name="uq_clustering_source_id"),
        sa.UniqueConstraint("source", "run_date", "calculation_version", "configuration_hash", name="uq_clustering_day_config"),
        sa.ForeignKeyConstraint(["source", "service_run_id"], ["service_runs.source", "service_runs.id"], name="fk_clustering_service", ondelete="RESTRICT"),
        sa.CheckConstraint("window_end > window_start AND input_cutoff >= window_end", name="ck_clustering_window"),
        sa.CheckConstraint("status IN ('running','success','insufficient_data','failed')", name="ck_clustering_status"), **options)
    op.create_index("ix_clustering_latest", "clustering_runs", ["source", "run_date", "status"])
    op.create_table("station_clusters",
        sa.Column("source", sa.String(32), primary_key=True),
        sa.Column("clustering_run_id", sa.Integer, primary_key=True),
        sa.Column("station_id", sa.String(128), primary_key=True),
        sa.Column("cluster_label", sa.Integer, nullable=False),
        sa.Column("distance_to_centroid", sa.Double, nullable=False),
        sa.Column("feature_values", sa.JSON, nullable=False),
        sa.Column("metadata_snapshot", sa.JSON, nullable=False),
        sa.Column("sample_count", sa.Integer, nullable=False),
        sa.Column("expected_sample_count", sa.Integer, nullable=False),
        sa.Column("coverage", sa.Double, nullable=False),
        sa.Column("profile", sa.JSON, nullable=False),
        sa.ForeignKeyConstraint(["source", "station_id"], ["stations.source", "stations.station_id"], name="fk_cluster_station", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source", "clustering_run_id"], ["clustering_runs.source", "clustering_runs.id"], name="fk_cluster_run", ondelete="RESTRICT"),
        sa.CheckConstraint("cluster_label >= 0 AND distance_to_centroid >= 0", name="ck_cluster_label_distance"),
        sa.CheckConstraint("sample_count > 0 AND expected_sample_count >= sample_count", name="ck_cluster_samples"),
        sa.CheckConstraint("coverage >= 0 AND coverage <= 1", name="ck_cluster_coverage"), **options)


def downgrade():
    raise RuntimeError("Forward-only: retain clustering snapshots and station memberships")
