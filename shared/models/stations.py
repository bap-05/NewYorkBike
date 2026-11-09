"""Persistent stations entities; timestamps use UTC."""
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, Double, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column
from shared.models.base import Base, UTCDateTime


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
