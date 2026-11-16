"""Persistent runs entities; timestamps use UTC."""
from datetime import date, datetime
from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, Double, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column
from shared.models.base import Base, UTCDateTime
from shared.database_names import db_table, db_column, db_foreign, db_check


class ServiceRun(Base):
    __tablename__ = db_table("service_runs")
    id: Mapped[int] = db_column("id", primary_key=True)
    service_name: Mapped[str] = db_column("service_name", String(32))
    source: Mapped[str] = db_column("source", String(32))
    scheduled_at: Mapped[datetime] = db_column("scheduled_at", UTCDateTime())
    started_at: Mapped[datetime] = db_column("started_at", UTCDateTime())
    finished_at: Mapped[datetime | None] = db_column("finished_at", UTCDateTime())
    heartbeat_at: Mapped[datetime] = db_column("heartbeat_at", UTCDateTime())
    input_watermark: Mapped[datetime | None] = db_column("input_watermark", UTCDateTime())
    status: Mapped[str] = db_column("status", String(16))
    attempt_count: Mapped[int] = db_column("attempt_count", default=1)
    calculation_version: Mapped[str] = db_column("calculation_version", String(32))
    configuration_hash: Mapped[str] = db_column("configuration_hash", String(64))
    configuration: Mapped[dict] = db_column("configuration", JSON)
    summary: Mapped[dict | None] = db_column("summary", JSON)
    result_count: Mapped[int] = db_column("result_count", default=0)
    error_summary: Mapped[str | None] = db_column("error_summary", String(255))
    __table_args__ = (
        UniqueConstraint("source", "id", name="uq_service_source_id"),
        UniqueConstraint("service_name", "source", "scheduled_at", "calculation_version", "configuration_hash", name="uq_service_period_config"),
        db_check("status IN ('running','success','skipped','failed')", name="ck_service_status"),
        db_check("attempt_count >= 1 AND result_count >= 0", name="ck_service_counts"),
        Index("ix_service_latest", "service_name", "source", "scheduled_at"),)
