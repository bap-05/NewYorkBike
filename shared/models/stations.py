"""Persistent stations entities; timestamps use UTC."""
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, Double, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column
from shared.models.base import Base, UTCDateTime
from shared.database_names import db_table, db_column, db_foreign, db_check


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
