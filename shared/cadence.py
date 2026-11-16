"""Declared sampling history, never inferred from missing observations.

Before the first transition each worker uses its configured legacy interval.
Transitions take effect at their UTC slot, including within an hour/local day.
"""
from bisect import bisect_right
from datetime import datetime, timedelta
import json
import os
from pathlib import Path

from shared.config import ROOT
from shared.time import UTC, as_utc


def validate_interval(seconds):
    if type(seconds) is not int or not 60 <= seconds <= 3600 or 3600 % seconds:
        raise ValueError('Sampling interval must divide 3600 and be in [60,3600]')


def normalize_changes(changes):
    result = []
    previous = None
    for effective_at, seconds in changes:
        validate_interval(seconds)
        try:
            instant = as_utc(datetime.fromisoformat(effective_at.replace('Z', '+00:00')))
        except (AttributeError, TypeError, ValueError):
            raise ValueError('Sampling transition must be an ISO timestamp with an offset') from None
        if instant.microsecond or int(instant.timestamp()) % seconds:
            raise ValueError('Sampling transition must align with its new interval')
        if previous is not None and instant <= previous:
            raise ValueError('Sampling transitions must be strictly chronological')
        result.append((instant.isoformat(), seconds))
        previous = instant
    return tuple(result)


def load_sampling_schedule():
    """Read non-secret repository configuration for the selected source only."""
    path = Path(os.getenv('SAMPLING_SCHEDULE_FILE', 'config/sampling_schedule.json'))
    if not path.is_absolute():
        path = ROOT / path
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        if payload['version'] != 1 or not isinstance(payload['sources'], dict):
            raise ValueError()
        rows = payload['sources'].get(os.getenv('BIKE_SOURCE', 'citibike'), [])
        if not isinstance(rows, list):
            raise ValueError()
        return normalize_changes((row['effective_at'], row['interval_seconds']) for row in rows)
    except (OSError, KeyError, TypeError, ValueError):
        raise ValueError('Invalid sampling schedule configuration; check SAMPLING_SCHEDULE_FILE') from None


class SamplingCadence:
    def __init__(self, initial_interval_seconds, changes=()):
        validate_interval(initial_interval_seconds)
        self.initial_interval_seconds = initial_interval_seconds
        self.changes = normalize_changes(changes)
        self.times = tuple(datetime.fromisoformat(at) for at, _ in self.changes)
        self.intervals = (initial_interval_seconds,) + tuple(seconds for _, seconds in self.changes)

    def interval_at(self, instant):
        return self.intervals[bisect_right(self.times, as_utc(instant))]

    def slot_at(self, instant):
        instant = as_utc(instant)
        seconds = self.interval_at(instant)
        return datetime.fromtimestamp(int(instant.timestamp()) // seconds * seconds, UTC)

    def slots(self, start, end):
        """Yield declared slots in [start,end), splitting exactly at transitions."""
        start, end = as_utc(start), as_utc(end)
        cursor = self.slot_at(start)
        if cursor < start:
            cursor = self.next_slot(cursor)
        while cursor < end:
            yield cursor
            cursor = self.next_slot(cursor)

    def next_slot(self, tick):
        tick = as_utc(tick)
        index = bisect_right(self.times, tick)
        candidate = tick + timedelta(seconds=self.intervals[index])
        return min(candidate, self.times[index]) if index < len(self.times) else candidate

    def adjacent(self, left, right):
        left, right = as_utc(left), as_utc(right)
        return left < right and self.next_slot(self.slot_at(left)) == self.slot_at(right)
