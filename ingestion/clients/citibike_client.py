"""Discover and join Citi Bike GBFS feeds. No API key or hardcoded child feed URLs."""
from datetime import datetime
import logging
from urllib.parse import urlsplit

from ingestion.clients.http import SourceError, get_json
from ingestion.normalizer import normalize_station
from shared.time import UTC, as_utc, utcnow

logger = logging.getLogger("ingestion")
SUPPORTED = {"1.1", "2.0", "2.1", "2.2", "2.3", "3.0"}


def gbfs_timestamp(value, version):
    """GBFS 1.x/2.x use Unix seconds; 3.0 uses RFC3339, never guess by magnitude."""
    try:
        if version == "3.0":
            if not isinstance(value, str):
                raise ValueError()
            return as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError()
        return datetime.fromtimestamp(value, UTC)
    except (ValueError, TypeError, OverflowError, OSError):
        raise SourceError("citibike: invalid GBFS timestamp for declared version") from None


def public_feed_url(url):
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError()
    except (ValueError, TypeError):
        raise SourceError("citibike: invalid discovery feed URL") from None
    return url


def station_index(payload):
    rows = payload.get("data", {}).get("stations")
    if not isinstance(rows, list):
        raise SourceError("citibike: missing station list")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise SourceError("citibike: invalid station row")
        station_id = row.get("station_id")
        if not isinstance(station_id, str) or not station_id or len(station_id) > 128:
            raise SourceError("citibike: station_id must be a non-empty string")
        if station_id in result:
            raise SourceError("citibike: duplicate station_id in feed")
        result[station_id] = row
    return result


class CitiBikeClient:
    def __init__(self, client, settings):
        self.client, self.settings = client, settings
        self.feed_metadata = {}

    def _feed(self, url, max_age):
        s = self.settings
        payload = get_json(self.client, public_feed_url(url), source="citibike", attempts=s.max_attempts,
                           backoff=s.backoff_seconds)
        collected_at = utcnow()
        version = payload.get("version")
        if not isinstance(version, str) or version not in SUPPORTED:
            raise SourceError("citibike: unsupported or missing GBFS version")
        updated = gbfs_timestamp(payload.get("last_updated"), version)
        age = (collected_at - updated).total_seconds()
        if age < -60 or age > max_age:
            raise SourceError("citibike: stale or future feed last_updated")
        ttl = payload.get("ttl")
        if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl < 0:
            raise SourceError("citibike: invalid feed ttl")
        if not isinstance(payload.get("data"), dict):
            raise SourceError("citibike: invalid feed data")
        return payload, collected_at, updated

    def fetch(self, station_ids=None):
        s = self.settings
        discovery, _, _ = self._feed(s.gbfs_discovery_url, s.gbfs_metadata_max_age_seconds)
        version = discovery["version"]
        data = discovery["data"]
        language_data = data if version == "3.0" else data.get("en", next(iter(data.values()), {}))
        feeds = language_data.get("feeds") if isinstance(language_data, dict) else None
        if not isinstance(feeds, list):
            raise SourceError("citibike: discovery feed list missing")
        urls = {}
        for feed in feeds:
            if isinstance(feed, dict) and feed.get("name") in ("station_information", "station_status"):
                if feed["name"] in urls:
                    raise SourceError("citibike: duplicate feed in discovery")
                urls[feed["name"]] = public_feed_url(feed.get("url"))
        if set(urls) != {"station_information", "station_status"}:
            raise SourceError("citibike: required feeds absent from discovery")
        info, info_received, info_updated = self._feed(urls["station_information"], s.gbfs_metadata_max_age_seconds)
        status, status_received, status_updated = self._feed(urls["station_status"], s.gbfs_status_max_age_seconds)
        if info["version"] != version or status["version"] != version:
            raise SourceError("citibike: discovery and child feed versions differ")
        information, statuses = station_index(info), station_index(status)
        self.feed_metadata = {"version": version, "discovery_url": s.gbfs_discovery_url,
            "station_information_url": urls["station_information"], "station_status_url": urls["station_status"],
            "information_last_updated": info_updated.isoformat(), "information_collected_at": info_received.isoformat(),
            "status_last_updated": status_updated.isoformat(), "status_collected_at": status_received.isoformat(),
            "status_ttl": status["ttl"], "information_count": len(information), "status_count": len(statuses)}
        logger.info("Citi Bike GBFS version=%s information=%s status=%s", version, len(information), len(statuses))
        wanted = set(station_ids) if station_ids else set(information)
        result = []
        for station_id in sorted(wanted & information.keys()):
            try:
                result.append(normalize_station(information[station_id], statuses.get(station_id),
                    version=version, collected_at=status_received, feed_last_updated=status_updated,
                    information_updated_at=info_updated, max_age=s.gbfs_status_max_age_seconds))
            except ValueError:
                logger.warning("citibike: station with invalid metadata skipped")
        return result
