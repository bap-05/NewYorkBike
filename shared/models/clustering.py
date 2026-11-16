"""Persistent clustering entities; timestamps use UTC."""
from datetime import date, datetime
from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, Double, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column
from shared.models.base import Base, UTCDateTime
from shared.database_names import db_table, db_column, db_foreign, db_check


class ClusteringRun(Base):
    __tablename__ = db_table("clustering_runs")
    id: Mapped[int] = db_column("id", primary_key=True)
    source: Mapped[str] = db_column("source", String(32))
    run_date: Mapped[date] = db_column("run_date", Date)
    service_run_id: Mapped[int] = db_column("service_run_id", Integer)
    window_start: Mapped[datetime] = db_column("window_start", UTCDateTime())
    window_end: Mapped[datetime] = db_column("window_end", UTCDateTime())
    input_cutoff: Mapped[datetime] = db_column("input_cutoff", UTCDateTime())
    started_at: Mapped[datetime] = db_column("started_at", UTCDateTime())
    finished_at: Mapped[datetime | None] = db_column("finished_at", UTCDateTime())
    status: Mapped[str] = db_column("status", String(24))
    algorithm: Mapped[str] = db_column("algorithm", String(64))
    calculation_version: Mapped[str] = db_column("calculation_version", String(32))
    configuration_hash: Mapped[str] = db_column("configuration_hash", String(64))
    feature_config: Mapped[dict] = db_column("feature_config", JSON)
    parameters: Mapped[dict | None] = db_column("parameters", JSON)
    summary: Mapped[dict | None] = db_column("summary", JSON)
    __table_args__ = (
        UniqueConstraint("source", "id", name="uq_clustering_source_id"),
        UniqueConstraint("source", "run_date", "calculation_version", "configuration_hash", name="uq_clustering_day_config"),
        ForeignKeyConstraint(["source", "service_run_id"], [db_foreign("service_runs.source"), db_foreign("service_runs.id")], name="fk_clustering_service", ondelete="RESTRICT"),
        db_check("window_end > window_start AND input_cutoff >= window_end", name="ck_clustering_window"),
        db_check("status IN ('running','success','insufficient_data','failed')", name="ck_clustering_status"),
        Index("ix_clustering_latest", "source", "run_date", "status"),)



class StationCluster(Base):
    __tablename__ = db_table("station_clusters")
    source: Mapped[str] = db_column("source", String(32), primary_key=True)
    clustering_run_id: Mapped[int] = db_column("clustering_run_id", Integer, primary_key=True)
    station_id: Mapped[str] = db_column("station_id", String(128), primary_key=True)
    cluster_label: Mapped[int] = db_column("cluster_label", Integer)
    distance_to_centroid: Mapped[float] = db_column("distance_to_centroid", Double)
    feature_values: Mapped[dict] = db_column("feature_values", JSON)
    metadata_snapshot: Mapped[dict] = db_column("metadata_snapshot", JSON)
    sample_count: Mapped[int] = db_column("sample_count", Integer)
    expected_sample_count: Mapped[int] = db_column("expected_sample_count", Integer)
    coverage: Mapped[float] = db_column("coverage", Double)
    profile: Mapped[dict] = db_column("profile", JSON)
    __table_args__ = (
        ForeignKeyConstraint(["source", "station_id"], [db_foreign("stations.source"), db_foreign("stations.station_id")], name="fk_cluster_station", ondelete="RESTRICT"),
        ForeignKeyConstraint(["source", "clustering_run_id"], [db_foreign("clustering_runs.source"), db_foreign("clustering_runs.id")], name="fk_cluster_run", ondelete="RESTRICT"),
        db_check("cluster_label >= 0 AND distance_to_centroid >= 0", name="ck_cluster_label_distance"),
        db_check("sample_count > 0 AND expected_sample_count >= sample_count", name="ck_cluster_samples"),
        db_check("coverage >= 0 AND coverage <= 1", name="ck_cluster_coverage"),)
