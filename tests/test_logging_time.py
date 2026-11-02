from datetime import datetime
import logging

import pytest

from shared.logging_config import ZonedFormatter
from shared.time import UTC


@pytest.mark.parametrize("instant,expected", [
    (datetime(2026, 11, 1, 5, 30, tzinfo=UTC), "2026-11-01T01:30:00.000-04:00"),
    (datetime(2026, 11, 1, 6, 30, tzinfo=UTC), "2026-11-01T01:30:00.000-05:00"),
])
def test_log_time_preserves_offset_when_new_york_hour_repeats(instant, expected):
    record = logging.LogRecord("ingestion", logging.INFO, __file__, 1, "test message", (), None)
    record.created = instant.timestamp()
    output = ZonedFormatter().format(record)
    assert output == expected + " [America/New_York] INFO test message"
