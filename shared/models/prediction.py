"""Persistent prediction entities; timestamps use UTC."""
from datetime import date, datetime
from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, Double, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column
from shared.models.base import Base, UTCDateTime


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32))
    identity_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    trained_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    train_start: Mapped[datetime | None] = mapped_column(UTCDateTime())
    train_end: Mapped[datetime | None] = mapped_column(UTCDateTime())
    feature_config: Mapped[dict] = mapped_column(JSON)
    metrics: Mapped[dict] = mapped_column(JSON)
    artifact: Mapped[dict] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        UniqueConstraint("source", "id", name="uq_model_source_id"),
        UniqueConstraint("source", "identity_hash", name="uq_model_identity"),
        CheckConstraint("kind IN ('persistence','random_forest')", name="ck_model_kind"),)



class TrainingJob(Base):
    __tablename__ = "training_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime())
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(24))
    parameters: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[dict | None] = mapped_column(JSON)
    model_version_id: Mapped[int | None] = mapped_column(Integer)
    error_summary: Mapped[str | None] = mapped_column(String(255))
    __table_args__ = (
        ForeignKeyConstraint(["source","model_version_id"],["model_versions.source","model_versions.id"], name="fk_training_model",ondelete="RESTRICT"),
        CheckConstraint("status IN ('running','success','insufficient_data','baseline_preferred','failed')",name="ck_training_status"),)



class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    station_id: Mapped[str] = mapped_column(String(128))
    service_run_id: Mapped[int] = mapped_column(Integer)
    scheduled_at: Mapped[datetime] = mapped_column(UTCDateTime())
    input_cutoff_at: Mapped[datetime] = mapped_column(UTCDateTime())
    input_time: Mapped[datetime | None] = mapped_column(UTCDateTime())
    target_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime())
    input_observation_id: Mapped[int | None] = mapped_column(ForeignKey("bike_observations.id",ondelete="RESTRICT"))
    model_version_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str | None] = mapped_column(String(128))
    raw_predicted_bikes: Mapped[float | None] = mapped_column(Double)
    predicted_bikes: Mapped[float | None] = mapped_column(Double)
    features: Mapped[dict] = mapped_column(JSON)
    actual_observation_id: Mapped[int | None] = mapped_column(ForeignKey("bike_observations.id",ondelete="RESTRICT"))
    evaluated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    actual_bikes: Mapped[int | None] = mapped_column(Integer)
    actual_time: Mapped[datetime | None] = mapped_column(UTCDateTime())
    target_offset_seconds: Mapped[float | None] = mapped_column(Double)
    absolute_error: Mapped[float | None] = mapped_column(Double)
    squared_error: Mapped[float | None] = mapped_column(Double)
    served_absolute_error: Mapped[float | None] = mapped_column(Double)
    __table_args__ = (
        UniqueConstraint("source","station_id","service_run_id",name="uq_prediction_service_station"),
        ForeignKeyConstraint(["source","station_id"],["stations.source","stations.station_id"],name="fk_prediction_station",ondelete="RESTRICT"),
        ForeignKeyConstraint(["source","service_run_id"],["service_runs.source","service_runs.id"],name="fk_prediction_service",ondelete="RESTRICT"),
        ForeignKeyConstraint(["source","model_version_id"],["model_versions.source","model_versions.id"],name="fk_prediction_model",ondelete="RESTRICT"),
        CheckConstraint("status IN ('baseline','ml','unavailable')",name="ck_prediction_status"),
        CheckConstraint("predicted_bikes IS NULL OR predicted_bikes >= 0",name="ck_prediction_nonnegative"),
        CheckConstraint("(status='unavailable' AND predicted_bikes IS NULL AND raw_predicted_bikes IS NULL) OR (status IN ('baseline','ml') AND predicted_bikes IS NOT NULL AND raw_predicted_bikes IS NOT NULL AND model_version_id IS NOT NULL AND input_observation_id IS NOT NULL AND input_time IS NOT NULL AND target_at IS NOT NULL AND target_at > issued_at)",name="ck_prediction_publication"),
        Index("ix_prediction_station_target","source","station_id","target_at"),)
