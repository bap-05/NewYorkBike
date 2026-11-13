"""Shared persistent entities. DATETIME(6) contains UTC, returned as aware UTC."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index,
                        Integer, Numeric, String, Text, UniqueConstraint)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy import Double
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from shared.time import UTC, as_utc
from shared.database_names import db_table, db_column, db_foreign, db_check


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(DATETIME(fsp=6) if dialect.name == "mysql" else DateTime())

    def process_bind_param(self, value, dialect):
        return None if value is None else as_utc(value).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    pass


class Station(Base):
    __tablename__ = db_table("stations")
    source: Mapped[str] = db_column("source", String(32), primary_key=True, default="seoul", server_default="seoul")
    station_id: Mapped[str] = db_column("station_id", String(128), primary_key=True)
    name: Mapped[str] = db_column("name", String(255))
    latitude: Mapped[Decimal] = db_column("latitude", Numeric(10, 6))
    longitude: Mapped[Decimal] = db_column("longitude", Numeric(10, 6))
    rack_count: Mapped[int | None] = db_column("rack_count", Integer)
    capacity: Mapped[int | None] = db_column("capacity", Integer)
    information_updated_at: Mapped[datetime | None] = db_column("information_updated_at", UTCDateTime())
    is_monitored: Mapped[bool] = db_column("is_monitored", Boolean, default=True)
    updated_at: Mapped[datetime] = db_column("updated_at", UTCDateTime())
    __table_args__ = (
        db_check("rack_count IS NULL OR rack_count >= 0", name="ck_station_racks"),
        db_check("capacity IS NULL OR capacity >= 0", name="ck_station_capacity"),
        db_check("latitude BETWEEN -90 AND 90", name="ck_station_latitude"),
        db_check("longitude BETWEEN -180 AND 180", name="ck_station_longitude"),
    )


class CollectionRun(Base):
    __tablename__ = db_table("collection_runs")
    id: Mapped[int] = db_column("id", primary_key=True)
    scheduled_at: Mapped[datetime] = db_column("scheduled_at", UTCDateTime())
    started_at: Mapped[datetime] = db_column("started_at", UTCDateTime())
    finished_at: Mapped[datetime | None] = db_column("finished_at", UTCDateTime())
    source: Mapped[str] = db_column("source", String(64), default="citibike")
    feed_metadata: Mapped[dict | None] = db_column("feed_metadata", JSON)
    bronze_manifest_path: Mapped[str | None] = db_column("bronze_manifest_path", String(1024))
    status: Mapped[str] = db_column("status", String(16))
    success_count: Mapped[int] = db_column("success_count", default=0)
    error_count: Mapped[int] = db_column("error_count", default=0)
    attempt_count: Mapped[int] = db_column("attempt_count", default=1)
    error_summary: Mapped[str | None] = db_column("error_summary", Text)
    __table_args__ = (
        UniqueConstraint("source", "scheduled_at", name="uq_run_source_sample"),
        db_check("status IN ('running','success','partial','failed')", name="ck_run_status"),)


class BikeObservation(Base):
    __tablename__ = db_table("bike_observations")
    id: Mapped[int] = db_column("id", primary_key=True)
    source: Mapped[str] = db_column("source", String(32), default="seoul", server_default="seoul")
    station_id: Mapped[str] = db_column("station_id", String(128))
    collection_run_id: Mapped[int] = db_column("collection_run_id", ForeignKey(db_foreign("collection_runs.id"), ondelete="RESTRICT"))
    sampled_at: Mapped[datetime] = db_column("sampled_at", UTCDateTime())
    collected_at: Mapped[datetime] = db_column("collected_at", UTCDateTime())
    source_observed_at: Mapped[datetime | None] = db_column("source_observed_at", UTCDateTime())
    available_bikes: Mapped[int | None] = db_column("available_bikes", Integer)
    available_docks: Mapped[int | None] = db_column("available_docks", Integer)
    is_installed: Mapped[bool | None] = db_column("is_installed", Boolean)
    is_renting: Mapped[bool | None] = db_column("is_renting", Boolean)
    is_returning: Mapped[bool | None] = db_column("is_returning", Boolean)
    feed_last_updated: Mapped[datetime | None] = db_column("feed_last_updated", UTCDateTime())
    gbfs_version: Mapped[str | None] = db_column("gbfs_version", String(8))
    quality_status: Mapped[str] = db_column("quality_status", String(32))
    __table_args__ = (
        ForeignKeyConstraint(["source", "station_id"], [db_foreign("stations.source"), db_foreign("stations.station_id")], name="fk_bike_source_station", ondelete="RESTRICT"),
        UniqueConstraint("source", "station_id", "sampled_at", name="uq_bike_source_station_sample"),
        Index("ix_bike_source_station_time", "source", "station_id", "collected_at"),
        Index("ix_bike_station_collected", "station_id", "collected_at"),
        Index("ix_bike_run", "collection_run_id"),
        db_check("available_bikes IS NULL OR available_bikes >= 0", name="ck_bike_count"),
        db_check("available_docks IS NULL OR available_docks >= 0", name="ck_bike_docks"),
        db_check("quality_status IN ('valid','missing','invalid','inactive','stale')", name="ck_bike_quality"),
    )


class WeatherObservation(Base):
    __tablename__ = db_table("weather_observations")
    id: Mapped[int] = db_column("id", primary_key=True)
    collection_run_id: Mapped[int | None] = db_column("collection_run_id", ForeignKey(db_foreign("collection_runs.id"), ondelete="RESTRICT"))
    requested_latitude: Mapped[Decimal] = db_column("requested_latitude", Numeric(10, 6))
    requested_longitude: Mapped[Decimal] = db_column("requested_longitude", Numeric(10, 6))
    returned_latitude: Mapped[Decimal | None] = db_column("returned_latitude", Numeric(10, 6))
    returned_longitude: Mapped[Decimal | None] = db_column("returned_longitude", Numeric(10, 6))
    weather_time: Mapped[datetime] = db_column("weather_time", UTCDateTime())
    collected_at: Mapped[datetime] = db_column("collected_at", UTCDateTime())
    temperature: Mapped[float | None] = db_column("temperature")
    humidity: Mapped[float | None] = db_column("humidity")
    rain: Mapped[float | None] = db_column("rain")
    wind_speed: Mapped[float | None] = db_column("wind_speed")
    units: Mapped[dict] = db_column("units", JSON)
    temperature_unit: Mapped[str | None] = db_column("temperature_unit", String(20))
    humidity_unit: Mapped[str | None] = db_column("humidity_unit", String(20))
    rain_unit: Mapped[str | None] = db_column("rain_unit", String(20))
    wind_speed_unit: Mapped[str | None] = db_column("wind_speed_unit", String(20))
    interval_seconds: Mapped[int] = db_column("interval_seconds", Integer)
    source: Mapped[str] = db_column("source", String(32), default="open-meteo")
    __table_args__ = (
        UniqueConstraint("requested_latitude", "requested_longitude", "weather_time", "source", name="uq_weather_location_time_source"),
        db_check("humidity IS NULL OR humidity BETWEEN 0 AND 100", name="ck_weather_humidity"),
        db_check("rain IS NULL OR rain >= 0", name="ck_weather_rain"),
        db_check("wind_speed IS NULL OR wind_speed >= 0", name="ck_weather_wind"),
        db_check("interval_seconds > 0", name="ck_weather_interval"),
    )


class ObservationWeatherLink(Base):
    __tablename__ = db_table("observation_weather_links")
    # Exactly one chosen weather observation per bike observation; many bikes may reuse weather.
    bike_observation_id: Mapped[int] = db_column("bike_observation_id", ForeignKey(db_foreign("bike_observations.id"), ondelete="RESTRICT"), primary_key=True)
    weather_observation_id: Mapped[int] = db_column("weather_observation_id", ForeignKey(db_foreign("weather_observations.id"), ondelete="RESTRICT"), index=True)


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
