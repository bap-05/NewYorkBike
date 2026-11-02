from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from ingestion import main
from ingestion.collector import collect_once
from shared.time import UTC, display_time, next_half_hour


@pytest.mark.parametrize("current,expected", [
    ("2026-11-02T13:47:12+00:00", "2026-11-02T14:00:00+00:00"),
    ("2026-11-02T14:00:00+00:00", "2026-11-02T14:30:00+00:00"),
    ("2026-11-02T14:29:59+00:00", "2026-11-02T14:30:00+00:00"),
    ("2026-11-02T14:30:00+00:00", "2026-11-02T15:00:00+00:00"),
    # Spring skips 02:00; fall goes back to 01:00 with a different UTC offset.
    ("2026-03-08T06:50:00+00:00", "2026-03-08T07:00:00+00:00"),
    ("2026-11-01T05:50:00+00:00", "2026-11-01T06:00:00+00:00"),
    ("2026-11-01T06:30:00+00:00", "2026-11-01T07:00:00+00:00"),
])
def test_next_new_york_wall_clock_boundary(current, expected):
    actual = next_half_hour(datetime.fromisoformat(current))
    assert actual == datetime.fromisoformat(expected)
    assert actual.astimezone(ZoneInfo("America/New_York")).minute in (0, 30)


def run_fake_scheduler(monkeypatch, settings, *, start, first_duration, stop_after):
    clock = [start]
    calls = []
    disposed = []

    @contextmanager
    def client(_):
        yield object()

    @contextmanager
    def session(_):
        yield object()

    def collect(_session, _bike, _weather, _ids, *, scheduled_at, bronze):
        calls.append(scheduled_at)
        if len(calls) == stop_after:
            raise KeyboardInterrupt()
        if len(calls) == 1:
            clock[0] += timedelta(seconds=first_duration)
        return SimpleNamespace(id=len(calls), scheduled_at=scheduled_at, status="success",
            success_count=1, error_count=0, attempt_count=1, error_summary=None, bronze_manifest_path=None)

    monkeypatch.setattr(main, "OutboundClient", client)
    monkeypatch.setattr(main, "ingestion_session", session)
    monkeypatch.setattr(main, "make_engine", lambda _: SimpleNamespace(dispose=lambda: disposed.append(True)))
    monkeypatch.setattr(main, "collect_once", collect)
    monkeypatch.setattr(main, "utcnow", lambda: clock[0])
    monkeypatch.setattr(main.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + timedelta(seconds=seconds)))
    with pytest.raises(KeyboardInterrupt):
        main.run(settings, schedule=True)
    assert disposed == [True]
    return calls


def test_collects_immediately_then_at_nine_and_nine_thirty(monkeypatch, settings):
    calls = run_fake_scheduler(monkeypatch, settings,
        start=datetime(2026, 11, 2, 13, 47, 12, tzinfo=UTC), first_duration=7, stop_after=3)
    assert [display_time(value) for value in calls] == [
        "2026-11-02T08:47:12-05:00", "2026-11-02T09:00:00-05:00", "2026-11-02T09:30:00-05:00"]


def test_does_not_overlap_or_backfill_boundary_passed_during_collection(monkeypatch, settings):
    calls = run_fake_scheduler(monkeypatch, settings,
        start=datetime(2026, 11, 2, 13, 59, 59, tzinfo=UTC), first_duration=6, stop_after=2)
    assert [display_time(value) for value in calls] == [
        "2026-11-02T08:59:59-05:00", "2026-11-02T09:30:00-05:00"]


def test_future_sample_is_rejected(session, settings, now):
    with pytest.raises(ValueError, match="future samples"):
        collect_once(session, None, None, settings.station_ids, scheduled_at=now + timedelta(minutes=1))
