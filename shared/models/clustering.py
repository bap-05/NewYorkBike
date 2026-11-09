"""Persistent clustering entities; timestamps use UTC."""
from datetime import date, datetime
from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, Double, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column
from shared.models.base import Base, UTCDateTime


class ClusteringRun(Base):
    __tablename__ = "clustering_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    run_date: Mapped[date] = mapped_column(Date)
    service_run_id: Mapped[int] = mapped_column(Integer)
    window_start: Mapped[datetime] = mapped_column(UTCDateTime())
    window_end: Mapped[datetime] = mapped_column(UTCDateTime())
    input_cutoff: Mapped[datetime] = mapped_column(UTCDateTime())
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(24))
    algorithm: Mapped[str] = mapped_column(String(64))
    calculation_version: Mapped[str] = mapped_column(String(32))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    feature_config: Mapped[dict] = mapped_column(JSON)
    parameters: Mapped[dict | None] = mapped_column(JSON)
    summary: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("source", "id", name="uq_clustering_source_id"),
        UniqueConstraint("source", "run_date", "calculation_version", "configuration_hash", name="uq_clustering_day_config"),
        ForeignKeyConstraint(["source", "service_run_id"], ["service_runs.source", "service_runs.id"], name="fk_clustering_service", ondelete="RESTRICT"),
        CheckConstraint("window_end > window_start AND input_cutoff >= window_end", name="ck_clustering_window"),
        CheckConstraint("status IN ('running','success','insufficient_data','failed')", name="ck_clustering_status"),
        Index("ix_clustering_latest", "source", "run_date", "status"),)



class StationCluster(Base):
    __tablename__ = "station_clusters"
    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    clustering_run_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    station_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    cluster_label: Mapped[int] = mapped_column(Integer)
    distance_to_centroid: Mapped[float] = mapped_column(Double)
    feature_values: Mapped[dict] = mapped_column(JSON)
    metadata_snapshot: Mapped[dict] = mapped_column(JSON)
    sample_count: Mapped[int] = mapped_column(Integer)
    expected_sample_count: Mapped[int] = mapped_column(Integer)
    coverage: Mapped[float] = mapped_column(Double)
    profile: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(["source", "station_id"], ["stations.source", "stations.station_id"], name="fk_cluster_station", ondelete="RESTRICT"),
        ForeignKeyConstraint(["source", "clustering_run_id"], ["clustering_runs.source", "clustering_runs.id"], name="fk_cluster_run", ondelete="RESTRICT"),
        CheckConstraint("cluster_label >= 0 AND distance_to_centroid >= 0", name="ck_cluster_label_distance"),
        CheckConstraint("sample_count > 0 AND expected_sample_count >= sample_count", name="ck_cluster_samples"),
        CheckConstraint("coverage >= 0 AND coverage <= 1", name="ck_cluster_coverage"),)
