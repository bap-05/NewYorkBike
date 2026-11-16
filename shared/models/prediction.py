"""Persistent prediction entities; timestamps use UTC."""
from datetime import date, datetime
from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, Double, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column
from shared.models.base import Base, UTCDateTime
from shared.database_names import db_table, db_column, db_foreign, db_check


class ModelVersion(Base):
    __tablename__ = db_table("model_versions")
    id: Mapped[int] = db_column("id", primary_key=True)
    source: Mapped[str] = db_column("source", String(32))
    name: Mapped[str] = db_column("name", String(128))
    kind: Mapped[str] = db_column("kind", String(32))
    identity_hash: Mapped[str] = db_column("identity_hash", String(64))
    created_at: Mapped[datetime] = db_column("created_at", UTCDateTime())
    trained_at: Mapped[datetime | None] = db_column("trained_at", UTCDateTime())
    train_start: Mapped[datetime | None] = db_column("train_start", UTCDateTime())
    train_end: Mapped[datetime | None] = db_column("train_end", UTCDateTime())
    feature_config: Mapped[dict] = db_column("feature_config", JSON)
    metrics: Mapped[dict] = db_column("metrics", JSON)
    artifact: Mapped[dict] = db_column("artifact", JSON)
    is_active: Mapped[bool] = db_column("is_active", Boolean, default=False)
    __table_args__ = (
        UniqueConstraint("source", "id", name="uq_model_source_id"),
        UniqueConstraint("source", "identity_hash", name="uq_model_identity"),
        db_check("kind IN ('persistence','random_forest')", name="ck_model_kind"),)



class TrainingJob(Base):
    __tablename__ = db_table("training_jobs")
    id: Mapped[int] = db_column("id", primary_key=True)
    source: Mapped[str] = db_column("source", String(32))
    requested_at: Mapped[datetime] = db_column("requested_at", UTCDateTime())
    started_at: Mapped[datetime] = db_column("started_at", UTCDateTime())
    finished_at: Mapped[datetime | None] = db_column("finished_at", UTCDateTime())
    status: Mapped[str] = db_column("status", String(24))
    parameters: Mapped[dict] = db_column("parameters", JSON)
    summary: Mapped[dict | None] = db_column("summary", JSON)
    model_version_id: Mapped[int | None] = db_column("model_version_id", Integer)
    error_summary: Mapped[str | None] = db_column("error_summary", String(255))
    __table_args__ = (
        ForeignKeyConstraint(["source","model_version_id"],[db_foreign("model_versions.source"),db_foreign("model_versions.id")], name="fk_training_model",ondelete="RESTRICT"),
        db_check("status IN ('running','success','insufficient_data','baseline_preferred','failed')",name="ck_training_status"),)



class Prediction(Base):
    __tablename__ = db_table("predictions")
    id: Mapped[int] = db_column("id", primary_key=True)
    source: Mapped[str] = db_column("source", String(32))
    station_id: Mapped[str] = db_column("station_id", String(128))
    service_run_id: Mapped[int] = db_column("service_run_id", Integer)
    scheduled_at: Mapped[datetime] = db_column("scheduled_at", UTCDateTime())
    input_cutoff_at: Mapped[datetime] = db_column("input_cutoff_at", UTCDateTime())
    input_time: Mapped[datetime | None] = db_column("input_time", UTCDateTime())
    target_at: Mapped[datetime | None] = db_column("target_at", UTCDateTime())
    issued_at: Mapped[datetime] = db_column("issued_at", UTCDateTime())
    input_observation_id: Mapped[int | None] = db_column("input_observation_id", ForeignKey(db_foreign("bike_observations.id"),ondelete="RESTRICT"))
    model_version_id: Mapped[int | None] = db_column("model_version_id", Integer)
    status: Mapped[str] = db_column("status", String(24))
    reason: Mapped[str | None] = db_column("reason", String(128))
    raw_predicted_bikes: Mapped[float | None] = db_column("raw_predicted_bikes", Double)
    predicted_bikes: Mapped[float | None] = db_column("predicted_bikes", Double)
    features: Mapped[dict] = db_column("features", JSON)
    actual_observation_id: Mapped[int | None] = db_column("actual_observation_id", ForeignKey(db_foreign("bike_observations.id"),ondelete="RESTRICT"))
    evaluated_at: Mapped[datetime | None] = db_column("evaluated_at", UTCDateTime())
    actual_bikes: Mapped[int | None] = db_column("actual_bikes", Integer)
    actual_time: Mapped[datetime | None] = db_column("actual_time", UTCDateTime())
    target_offset_seconds: Mapped[float | None] = db_column("target_offset_seconds", Double)
    absolute_error: Mapped[float | None] = db_column("absolute_error", Double)
    squared_error: Mapped[float | None] = db_column("squared_error", Double)
    served_absolute_error: Mapped[float | None] = db_column("served_absolute_error", Double)
    __table_args__ = (
        UniqueConstraint("source","station_id","service_run_id",name="uq_prediction_service_station"),
        ForeignKeyConstraint(["source","station_id"],[db_foreign("stations.source"),db_foreign("stations.station_id")],name="fk_prediction_station",ondelete="RESTRICT"),
        ForeignKeyConstraint(["source","service_run_id"],[db_foreign("service_runs.source"),db_foreign("service_runs.id")],name="fk_prediction_service",ondelete="RESTRICT"),
        ForeignKeyConstraint(["source","model_version_id"],[db_foreign("model_versions.source"),db_foreign("model_versions.id")],name="fk_prediction_model",ondelete="RESTRICT"),
        db_check("status IN ('baseline','ml','unavailable')",name="ck_prediction_status"),
        db_check("predicted_bikes IS NULL OR predicted_bikes >= 0",name="ck_prediction_nonnegative"),
        db_check("(status='unavailable' AND predicted_bikes IS NULL AND raw_predicted_bikes IS NULL) OR (status IN ('baseline','ml') AND predicted_bikes IS NOT NULL AND raw_predicted_bikes IS NOT NULL AND model_version_id IS NOT NULL AND input_observation_id IS NOT NULL AND input_time IS NOT NULL AND target_at IS NOT NULL AND target_at > issued_at)",name="ck_prediction_publication"),
        Index("ix_prediction_station_target","source","station_id","target_at"),)
