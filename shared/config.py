"""Load secrets only on explicit startup, never on import."""
import os
import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from sqlalchemy import URL

ROOT = Path(__file__).resolve().parents[1]


def integer(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if not low <= value <= high:
        raise ValueError(f"{name} must be in [{low}, {high}]")
    return value


def proxy_config() -> tuple[bool, tuple[str, ...]]:
    flag = os.getenv("OUTBOUND_PROXY_ENABLED", "false").strip().lower()
    if flag not in ("true", "false"):
        raise ValueError("OUTBOUND_PROXY_ENABLED must be true or false")
    try:
        values = json.loads(os.getenv("OUTBOUND_PROXY_URLS", "[]"))
    except (ValueError, TypeError):
        raise ValueError("OUTBOUND_PROXY_URLS must be a JSON array of proxy URLs") from None
    if not isinstance(values, list) or len(values) > 64:
        raise ValueError("OUTBOUND_PROXY_URLS must be a JSON array with at most 64 URLs")
    for value in values:
        try:
            if not isinstance(value, str) or any(char.isspace() for char in value):
                raise ValueError()
            parsed = urlsplit(value)
            if (parsed.scheme not in ("http", "https") or not parsed.hostname
                    or not parsed.port or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
                raise ValueError()
        except ValueError:
            # Proxy URLs may contain credentials: never interpolate them into an error.
            raise ValueError("OUTBOUND_PROXY_URLS: use http(s)://[user:password@]host:port without path/query; encode credentials") from None
    urls = tuple(dict.fromkeys(values))
    enabled = flag == "true"
    if enabled and not urls:
        raise ValueError("OUTBOUND_PROXY_ENABLED=true requires at least one URL in OUTBOUND_PROXY_URLS")
    return enabled, urls


@dataclass(frozen=True)
class Settings:
    mysql_host: str
    mysql_port: int
    mysql_database: str
    mysql_user: str
    mysql_password: str = field(repr=False)
    station_ids: tuple[str, ...]
    weather_url: str
    weather_max_age_seconds: int
    timeout_seconds: int
    max_attempts: int
    backoff_seconds: int
    bike_source: str = "citibike"
    gbfs_discovery_url: str = "https://gbfs.citibikenyc.com/gbfs/gbfs.json"
    gbfs_status_max_age_seconds: int = 600
    gbfs_metadata_max_age_seconds: int = 86400
    display_timezone: str = "America/New_York"
    proxy_enabled: bool = False
    proxy_urls: tuple[str, ...] = field(default=(), repr=False)
    bronze_dir: Path = ROOT / "data" / "bronze"
    mysql_ssl_ca: Path | None = None

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv(ROOT / ".env", override=False)
        proxy_enabled, proxy_urls = proxy_config()
        settings = cls(
            mysql_host=os.getenv("MYSQL_HOST", "127.0.0.1"),
            mysql_port=integer("MYSQL_PORT", 3306, 1, 65535),
            mysql_database=os.getenv("MYSQL_DATABASE", "seoul_bike"),
            mysql_user=os.getenv("MYSQL_USER", ""),
            mysql_password=os.getenv("MYSQL_PASSWORD", ""),
            mysql_ssl_ca=(ROOT / os.environ["MYSQL_SSL_CA"].strip()).resolve() if os.getenv("MYSQL_SSL_CA", "").strip() else None,
            station_ids=tuple(dict.fromkeys(x.strip() for x in os.getenv("STATION_IDS", "").split(",") if x.strip())),
            weather_url=os.getenv("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast"),
            weather_max_age_seconds=integer("WEATHER_MAX_AGE_SECONDS", 3600, 1, 86400),
            timeout_seconds=integer("HTTP_TIMEOUT_SECONDS", 20, 1, 120),
            max_attempts=integer("HTTP_MAX_ATTEMPTS", 3, 1, 5),
            backoff_seconds=integer("HTTP_BACKOFF_SECONDS", 1, 0, 30),
            bike_source=os.getenv("BIKE_SOURCE", "citibike"),
            gbfs_discovery_url=os.getenv("GBFS_DISCOVERY_URL", "https://gbfs.citibikenyc.com/gbfs/gbfs.json"),
            gbfs_status_max_age_seconds=integer("GBFS_STATUS_MAX_AGE_SECONDS", 600, 60, 86400),
            gbfs_metadata_max_age_seconds=integer("GBFS_METADATA_MAX_AGE_SECONDS", 86400, 60, 604800),
            display_timezone=os.getenv("DISPLAY_TIMEZONE", "America/New_York"),
            proxy_enabled=proxy_enabled,
            proxy_urls=proxy_urls,
            bronze_dir=(ROOT / os.getenv("BRONZE_DIR", "data/bronze")).resolve(),
        )
        for name, url in (("GBFS_DISCOVERY_URL", settings.gbfs_discovery_url), ("OPEN_METEO_URL", settings.weather_url)):
            parsed = urlsplit(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError(f"Invalid {name}")
        if settings.bike_source != "citibike":
            raise ValueError("BIKE_SOURCE must be citibike; legacy Seoul data remains readable in MySQL")
        try:
            ZoneInfo(settings.display_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Invalid DISPLAY_TIMEZONE; install tzdata on Windows") from None
        return settings

    def database_url(self) -> URL:
        if not self.mysql_user or not self.mysql_database:
            raise ValueError("Fill MYSQL_USER, MYSQL_PASSWORD and MYSQL_DATABASE in .env")
        return URL.create("mysql+pymysql", username=self.mysql_user, password=self.mysql_password,
                          host=self.mysql_host, port=self.mysql_port, database=self.mysql_database,
                          query={"charset": "utf8mb4"})

