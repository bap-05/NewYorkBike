"""Human-facing service logs use New York time, independent of the Windows timezone."""
from datetime import datetime
import logging
from zoneinfo import ZoneInfo

from shared.presentation import DISPLAY_TIMEZONE
from shared.time import UTC


class ZonedFormatter(logging.Formatter):
    def __init__(self, timezone_name=DISPLAY_TIMEZONE):
        super().__init__("%(asctime)s %(levelname)s %(message)s")
        self.timezone_name = timezone_name
        self.zone = ZoneInfo(timezone_name)

    def formatTime(self, record, datefmt=None):
        local = datetime.fromtimestamp(record.created, UTC).astimezone(self.zone)
        timestamp = local.strftime(datefmt) if datefmt else local.isoformat(timespec="milliseconds")
        return f"{timestamp} [{self.timezone_name}]"


def configure_logging(timezone_name=DISPLAY_TIMEZONE):
    handler = logging.StreamHandler()
    handler.setFormatter(ZonedFormatter(timezone_name))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
