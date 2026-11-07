"""Shared persistent entities. DATETIME(6) contains UTC, returned as aware UTC."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (JSON, Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index,
                        Integer, Numeric, String, Text, UniqueConstraint)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy import Double
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from shared.time import UTC, as_utc


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
    __tablename__ = "stations"
    source: Mapped[str] = mapped_column(String(32), primary_key=True, default="seoul", server_default="seoul")
    station_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    rack_count: Mapped[int | None] = mapped_column(Integer)
    capacity: Mapped[int | None] = mapped_column(Integer)
    information_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    is_monitored: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime())
    __table_args__ = (
        CheckConstraint("rack_count IS NULL OR rack_count >= 0", name="ck_station_racks"),
        CheckConstraint("capacity IS NULL OR capacity >= 0", name="ck_station_capacity"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_station_latitude"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_station_longitude"),
    )


class CollectionRun(Base):
    __tablename__ = "collection_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    scheduled_at: Mapped[datetime] = mapped_column(UTCDateTime())
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    source: Mapped[str] = mapped_column(String(64), default="citibike")
    feed_metadata: Mapped[dict | None] = mapped_column(JSON)
    bronze_manifest_path: Mapped[str | None] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(16))
    success_count: Mapped[int] = mapped_column(default=0)
    error_count: Mapped[int] = mapped_column(default=0)
    attempt_count: Mapped[int] = mapped_column(default=1)
    error_summary: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("source", "scheduled_at", name="uq_run_source_sample"),
        CheckConstraint("status IN ('running','success','partial','failed')", name="ck_run_status"),)


class BikeObservation(Base):
    __tablename__ = "bike_observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), default="seoul", server_default="seoul")
    station_id: Mapped[str] = mapped_column(String(128))
    collection_run_id: Mapped[int] = mapped_column(ForeignKey("collection_runs.id", ondelete="RESTRICT"))
    sampled_at: Mapped[datetime] = mapped_column(UTCDateTime())
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime())
    source_observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    available_bikes: Mapped[int | None] = mapped_column(Integer)
    available_docks: Mapped[int | None] = mapped_column(Integer)
    is_installed: Mapped[bool | None] = mapped_column(Boolean)
    is_renting: Mapped[bool | None] = mapped_column(Boolean)
    is_returning: Mapped[bool | None] = mapped_column(Boolean)
    feed_last_updated: Mapped[datetime | None] = mapped_column(UTCDateTime())
    gbfs_version: Mapped[str | None] = mapped_column(String(8))
    quality_status: Mapped[str] = mapped_column(String(32))
    __table_args__ = (
        ForeignKeyConstraint(["source", "station_id"], ["stations.source", "stations.station_id"], name="fk_bike_source_station", ondelete="RESTRICT"),
        UniqueConstraint("source", "station_id", "sampled_at", name="uq_bike_source_station_sample"),
        Index("ix_bike_source_station_time", "source", "station_id", "collected_at"),
        Index("ix_bike_station_collected", "station_id", "collected_at"),
        Index("ix_bike_run", "collection_run_id"),
        CheckConstraint("available_bikes IS NULL OR available_bikes >= 0", name="ck_bike_count"),
        CheckConstraint("available_docks IS NULL OR available_docks >= 0", name="ck_bike_docks"),
        CheckConstraint("quality_status IN ('valid','missing','invalid','inactive','stale')", name="ck_bike_quality"),
    )


class WeatherObservation(Base):
    __tablename__ = "weather_observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    collection_run_id: Mapped[int | None] = mapped_column(ForeignKey("collection_runs.id", ondelete="RESTRICT"))
    requested_latitude: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    requested_longitude: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    returned_latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    returned_longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    weather_time: Mapped[datetime] = mapped_column(UTCDateTime())
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime())
    temperature: Mapped[float | None]
    humidity: Mapped[float | None]
    rain: Mapped[float | None]
    wind_speed: Mapped[float | None]
    units: Mapped[dict] = mapped_column(JSON)
    temperature_unit: Mapped[str | None] = mapped_column(String(20))
    humidity_unit: Mapped[str | None] = mapped_column(String(20))
    rain_unit: Mapped[str | None] = mapped_column(String(20))
    wind_speed_unit: Mapped[str | None] = mapped_column(String(20))
    interval_seconds: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(32), default="open-meteo")
    __table_args__ = (
        UniqueConstraint("requested_latitude", "requested_longitude", "weather_time", "source", name="uq_weather_location_time_source"),
        CheckConstraint("humidity IS NULL OR humidity BETWEEN 0 AND 100", name="ck_weather_humidity"),
        CheckConstraint("rain IS NULL OR rain >= 0", name="ck_weather_rain"),
        CheckConstraint("wind_speed IS NULL OR wind_speed >= 0", name="ck_weather_wind"),
        CheckConstraint("interval_seconds > 0", name="ck_weather_interval"),
    )


class ObservationWeatherLink(Base):
    __tablename__ = "observation_weather_links"
    # Exactly one chosen weather observation per bike observation; many bikes may reuse weather.
    bike_observation_id: Mapped[int] = mapped_column(ForeignKey("bike_observations.id", ondelete="RESTRICT"), primary_key=True)
    weather_observation_id: Mapped[int] = mapped_column(ForeignKey("weather_observations.id", ondelete="RESTRICT"), index=True)


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
