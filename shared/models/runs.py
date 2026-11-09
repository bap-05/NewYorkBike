"""Persistent runs entities; timestamps use UTC."""
from datetime import date, datetime
from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, Double, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column
from shared.models.base import Base, UTCDateTime


class ServiceRun(Base):
    __tablename__ = "service_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    service_name: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(32))
    scheduled_at: Mapped[datetime] = mapped_column(UTCDateTime())
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    heartbeat_at: Mapped[datetime] = mapped_column(UTCDateTime())
    input_watermark: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(16))
    attempt_count: Mapped[int] = mapped_column(default=1)
    calculation_version: Mapped[str] = mapped_column(String(32))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    configuration: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[dict | None] = mapped_column(JSON)
    result_count: Mapped[int] = mapped_column(default=0)
    error_summary: Mapped[str | None] = mapped_column(String(255))
    __table_args__ = (
        UniqueConstraint("source", "id", name="uq_service_source_id"),
        UniqueConstraint("service_name", "source", "scheduled_at", "calculation_version", "configuration_hash", name="uq_service_period_config"),
        CheckConstraint("status IN ('running','success','skipped','failed')", name="ck_service_status"),
        CheckConstraint("attempt_count >= 1 AND result_count >= 0", name="ck_service_counts"),
        Index("ix_service_latest", "service_name", "source", "scheduled_at"),)
