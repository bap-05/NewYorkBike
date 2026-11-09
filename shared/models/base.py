"""Shared SQLAlchemy metadata and aware UTC database timestamps."""
from sqlalchemy import DateTime
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase
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
