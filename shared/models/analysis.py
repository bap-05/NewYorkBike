"""Persistent analysis entities; timestamps use UTC."""
from datetime import date, datetime
from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, Double, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column
from shared.models.base import Base, UTCDateTime


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    station_id: Mapped[str] = mapped_column(String(128))
    window_start: Mapped[datetime] = mapped_column(UTCDateTime())
    window_end: Mapped[datetime] = mapped_column(UTCDateTime())
    aggregation: Mapped[str] = mapped_column(String(16))
    metric_name: Mapped[str] = mapped_column(String(64))
    metric_value: Mapped[float | None] = mapped_column(Double)
    sample_count: Mapped[int] = mapped_column(Integer)
    observed_sample_count: Mapped[int] = mapped_column(Integer)
    expected_sample_count: Mapped[int] = mapped_column(Integer)
    coverage: Mapped[float | None] = mapped_column(Double)
    quality_status: Mapped[str] = mapped_column(String(24))
    dimensions: Mapped[dict] = mapped_column(JSON)
    input_cutoff: Mapped[datetime] = mapped_column(UTCDateTime())
    input_watermark: Mapped[datetime | None] = mapped_column(UTCDateTime())
    calculated_at: Mapped[datetime] = mapped_column(UTCDateTime())
    calculation_version: Mapped[str] = mapped_column(String(32))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    service_run_id: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        ForeignKeyConstraint(["source", "station_id"], ["stations.source", "stations.station_id"], name="fk_analysis_station", ondelete="RESTRICT"),
        ForeignKeyConstraint(["source", "service_run_id"], ["service_runs.source", "service_runs.id"], name="fk_analysis_service", ondelete="RESTRICT"),
        UniqueConstraint("source", "station_id", "window_start", "window_end", "aggregation", "metric_name", "calculation_version", "configuration_hash", name="uq_analysis_window_metric"),
        CheckConstraint("window_end > window_start", name="ck_analysis_window"),
        CheckConstraint("aggregation IN ('hour','day')", name="ck_analysis_aggregation"),
        CheckConstraint("sample_count >= 0 AND observed_sample_count >= 0 AND expected_sample_count >= 0", name="ck_analysis_counts"),
        CheckConstraint("coverage IS NULL OR (coverage >= 0 AND coverage <= 1)", name="ck_analysis_coverage"),
        CheckConstraint("quality_status IN ('ok','low_coverage','insufficient_data')", name="ck_analysis_quality"),
        Index("ix_analysis_station_window", "source", "station_id", "window_start"),)
