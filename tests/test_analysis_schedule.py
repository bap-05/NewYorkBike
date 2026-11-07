from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from analysis import main
from analysis.config import AnalysisOptions
from analysis.statistics import period_start
from shared.time import UTC


def scheduled_calls(monkeypatch, settings, *, start, duration=0):
    clock = [datetime.fromisoformat(start)]
    calls = []
    disposed = []
    @contextmanager
    def locked_session(engine, name):
        assert name == "analysis"
        yield object()
    def calculate(*args, **kwargs):
        calls.append(clock[0])
        if len(calls) == 3:
            raise KeyboardInterrupt()
        result = SimpleNamespace(id=len(calls), scheduled_at=period_start(clock[0],300),
            status="skipped", result_count=0, attempt_count=1, summary={})
        if len(calls) == 1:
            clock[0] += timedelta(seconds=duration)
        return result
    monkeypatch.setattr(main,"make_engine",lambda settings:SimpleNamespace(dispose=lambda:disposed.append(True)))
    monkeypatch.setattr(main,"service_session",locked_session)
    monkeypatch.setattr(main,"analyze_once",calculate)
    monkeypatch.setattr(main,"utcnow",lambda:clock[0])
    monkeypatch.setattr(main.time,"sleep",lambda seconds:clock.__setitem__(0,clock[0]+timedelta(seconds=seconds)))
    with pytest.raises(KeyboardInterrupt):
        main.run(settings,AnalysisOptions(),schedule=True)
    assert disposed == [True]
    return [value.isoformat() for value in calls]


def test_analysis_runs_independently_now_then_five_minute_boundaries(monkeypatch,settings):
    assert scheduled_calls(monkeypatch,settings,start="2026-01-01T12:02:10+00:00") == [
        "2026-01-01T12:02:10+00:00","2026-01-01T12:05:00+00:00","2026-01-01T12:10:00+00:00"]


def test_slow_analysis_skips_boundary_without_overlap(monkeypatch,settings):
    assert scheduled_calls(monkeypatch,settings,start="2026-01-01T12:04:59+00:00",duration=12) == [
        "2026-01-01T12:04:59+00:00","2026-01-01T12:10:00+00:00","2026-01-01T12:15:00+00:00"]


def test_analysis_scheduler_uses_utc_across_fall_dst(monkeypatch,settings):
    assert scheduled_calls(monkeypatch,settings,start="2026-11-01T05:58:10+00:00") == [
        "2026-11-01T05:58:10+00:00","2026-11-01T06:00:00+00:00","2026-11-01T06:05:00+00:00"]


def test_analysis_config_does_not_depend_on_proxy_credentials(monkeypatch):
    from shared.config import Settings
    monkeypatch.setenv("OUTBOUND_PROXY_ENABLED","true")
    monkeypatch.setenv("OUTBOUND_PROXY_URLS","not-json-or-a-real-secret")
    assert Settings.load(outbound=False).proxy_enabled is False
