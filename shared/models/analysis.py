"""Persistent analysis entities; timestamps use UTC."""
from datetime import date, datetime
from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, Double, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column
from shared.models.base import Base, UTCDateTime
from shared.database_names import db_table, db_column, db_foreign, db_check


class AnalysisResult(Base):
    __tablename__ = db_table("analysis_results")
    id: Mapped[int] = db_column("id", primary_key=True)
    source: Mapped[str] = db_column("source", String(32))
    station_id: Mapped[str] = db_column("station_id", String(128))
    window_start: Mapped[datetime] = db_column("window_start", UTCDateTime())
    window_end: Mapped[datetime] = db_column("window_end", UTCDateTime())
    aggregation: Mapped[str] = db_column("aggregation", String(16))
    metric_name: Mapped[str] = db_column("metric_name", String(64))
    metric_value: Mapped[float | None] = db_column("metric_value", Double)
    sample_count: Mapped[int] = db_column("sample_count", Integer)
    observed_sample_count: Mapped[int] = db_column("observed_sample_count", Integer)
    expected_sample_count: Mapped[int] = db_column("expected_sample_count", Integer)
    coverage: Mapped[float | None] = db_column("coverage", Double)
    quality_status: Mapped[str] = db_column("quality_status", String(24))
    dimensions: Mapped[dict] = db_column("dimensions", JSON)
    input_cutoff: Mapped[datetime] = db_column("input_cutoff", UTCDateTime())
    input_watermark: Mapped[datetime | None] = db_column("input_watermark", UTCDateTime())
    calculated_at: Mapped[datetime] = db_column("calculated_at", UTCDateTime())
    calculation_version: Mapped[str] = db_column("calculation_version", String(32))
    configuration_hash: Mapped[str] = db_column("configuration_hash", String(64))
    service_run_id: Mapped[int] = db_column("service_run_id", Integer)
    __table_args__ = (
        ForeignKeyConstraint(["source", "station_id"], [db_foreign("stations.source"), db_foreign("stations.station_id")], name="fk_analysis_station", ondelete="RESTRICT"),
        ForeignKeyConstraint(["source", "service_run_id"], [db_foreign("service_runs.source"), db_foreign("service_runs.id")], name="fk_analysis_service", ondelete="RESTRICT"),
        UniqueConstraint("source", "station_id", "window_start", "window_end", "aggregation", "metric_name", "calculation_version", "configuration_hash", name="uq_analysis_window_metric"),
        db_check("window_end > window_start", name="ck_analysis_window"),
        db_check("aggregation IN ('hour','day')", name="ck_analysis_aggregation"),
        db_check("sample_count >= 0 AND observed_sample_count >= 0 AND expected_sample_count >= 0", name="ck_analysis_counts"),
        db_check("coverage IS NULL OR (coverage >= 0 AND coverage <= 1)", name="ck_analysis_coverage"),
        db_check("quality_status IN ('ok','low_coverage','insufficient_data')", name="ck_analysis_quality"),
        Index("ix_analysis_station_window", "source", "station_id", "window_start"),)
