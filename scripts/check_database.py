"""Check the configured MySQL connection without migrations or data writes."""
from sqlalchemy import text

from shared.config import Settings
from shared.database import make_engine


def main():
    engine = None
    try:
        settings = Settings.load()
        engine = make_engine(settings)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            timezone = connection.scalar(text("SELECT @@session.time_zone"))
            row = connection.execute(text("SHOW SESSION STATUS LIKE 'Ssl_cipher'")).first()
            encrypted = bool(row and row[1])
            print("MySQL connection: OK")
            print(f"Session timezone: {timezone}")
            print("TLS: " + ("encrypted" if encrypted else "not enabled"))
            print("CA and hostname verification: " + ("required" if settings.mysql_ssl_ca else "not configured"))
            print("No migrations or application data writes performed.")
        return 0
    except Exception as exc:
        # Even driver exceptions may include host/user/credentials. Never print them.
        print(f"MySQL connection: FAILED ({type(exc).__name__})")
        print("Check MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD,")
        print("MYSQL_SSL_CA (valid PEM), service status and network access rules.")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
