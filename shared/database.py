from contextlib import contextmanager
import hashlib
import ssl

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from shared.config import Settings


def make_engine(settings: Settings):
    connect_args = {"connect_timeout": 10, "read_timeout": 30, "write_timeout": 30}
    if settings.mysql_ssl_ca is not None:
        try:
            # Verify both the CA chain and the server hostname (use Aiven's DNS host).
            connect_args["ssl"] = ssl.create_default_context(cafile=str(settings.mysql_ssl_ca))
        except (OSError, ssl.SSLError):
            raise ValueError("MYSQL_SSL_CA must point to a readable, valid PEM CA certificate") from None
    engine = create_engine(settings.database_url(), pool_pre_ping=True, pool_recycle=1800,
                           connect_args=connect_args,
                           hide_parameters=True)

    @event.listens_for(engine, "connect")
    def configure_connection(connection, _):
        with connection.cursor() as cursor:
            if settings.mysql_ssl_ca is not None:
                cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
                row = cursor.fetchone()
                if not row or not row[1]:
                    raise RuntimeError("MySQL TLS is required when MYSQL_SSL_CA is configured")
            cursor.execute("SET time_zone = '+00:00'")
            # SQLAlchemy detects identifier quoting during dialect initialization.
            # Preserve server modes such as ANSI_QUOTES (Aiven) rather than
            # changing quoting rules after that detection has already happened.
            cursor.execute("SELECT @@session.sql_mode")
            current_modes = cursor.fetchone()[0] or ""
            modes = {mode.strip() for mode in current_modes.split(",") if mode.strip()}
            modes.update({"STRICT_TRANS_TABLES", "NO_ZERO_DATE", "NO_ZERO_IN_DATE",
                          "ERROR_FOR_DIVISION_BY_ZERO", "NO_ENGINE_SUBSTITUTION"})
            cursor.execute("SET SESSION sql_mode = %s", (",".join(sorted(modes)),))

    return engine


@contextmanager
def ingestion_session(engine):
    """Dedicated connection: MySQL GET_LOCK survives commits and releases on disconnect."""
    lock_name = "seoul_ingestion_" + hashlib.sha256(str(engine.url.database).encode()).hexdigest()[:32]
    with engine.connect() as connection:
        acquired = connection.scalar(text("SELECT GET_LOCK(:name, 0)"), {"name": lock_name})
        connection.commit()
        if acquired != 1:
            raise RuntimeError("Another ingestion process holds the database lock")
        try:
            with Session(bind=connection, expire_on_commit=False) as session:
                yield session
        finally:
            connection.rollback()
            connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": lock_name})
            connection.commit()


@contextmanager
def service_session(engine, service_name):
    """A separate MySQL advisory lock per independent worker, across commits."""
    if service_name not in ("analysis", "clustering", "prediction"):
        raise ValueError("Unknown independent service")
    lock_name = "service_" + service_name + "_" + hashlib.sha256(str(engine.url.database).encode()).hexdigest()[:32]
    with engine.connect() as connection:
        acquired = connection.scalar(text("SELECT GET_LOCK(:name, 0)"), {"name": lock_name})
        connection.commit()
        if acquired != 1:
            raise RuntimeError("Another instance of this service holds the database lock")
        try:
            with Session(bind=connection, expire_on_commit=False) as session:
                yield session
        finally:
            connection.rollback()
            connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": lock_name})
            connection.commit()
