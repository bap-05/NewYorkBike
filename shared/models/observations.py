"""Persistent observations entities; timestamps use UTC."""
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, Double, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column
from shared.models.base import Base, UTCDateTime
from shared.database_names import db_table, db_column, db_foreign, db_check


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
    temperature: Mapped[float | None] = db_column('temperature')
    humidity: Mapped[float | None] = db_column('humidity')
    rain: Mapped[float | None] = db_column('rain')
    wind_speed: Mapped[float | None] = db_column('wind_speed')
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
