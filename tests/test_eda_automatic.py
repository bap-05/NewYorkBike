"""Background reports publish atomically and retry without losing the old snapshot."""
import asyncio
from datetime import datetime, timedelta, timezone
import json

import pytest

from eda.automatic import refresh_report, report_lock


def test_skip_unchanged_and_rebuild_after_late_import_or_missing_report(tmp_path):
    now = datetime(2026, 11, 16, tzinfo=timezone.utc)
    version = ['first']
    calls = []

    def generate(*args, output, **kwargs):
        calls.append(output)
        assert output.name.startswith('.pending-')
        output.mkdir()
        (output / 'report.html').write_text('complete')
        (output / 'summary.json').write_text('{}')

    def refresh():
        return refresh_report(None, None, root=tmp_path, clock=lambda: now,
            signature=lambda *a, **k: version[0], generate=generate)

    assert refresh() == 'updated'
    assert refresh() == 'unchanged'
    version[0] = 'historical-import-with-old-sampled-at'
    now += timedelta(minutes=15)
    assert refresh() == 'updated'
    state = json.loads((tmp_path / '.automatic.json').read_text())
    (tmp_path / state['report_id'] / 'report.html').unlink()
    now += timedelta(minutes=15)
    assert refresh() == 'updated'
    assert len(calls) == 3


def test_failed_render_keeps_last_completed_report_and_does_not_advance_state(tmp_path):
    (tmp_path / '.automatic.json').write_text('{"signature":"old","report_id":"old"}')
    (tmp_path / 'old').mkdir()
    (tmp_path / 'old' / 'report.html').write_text('old complete report')

    def broken(*args, output, **kwargs):
        output.mkdir()
        (output / 'partial.png').write_bytes(b'partial')
        raise RuntimeError('render failed')

    with pytest.raises(RuntimeError):
        refresh_report(None, None, root=tmp_path, signature=lambda *a, **k: 'new', generate=broken)
    assert json.loads((tmp_path / '.automatic.json').read_text())['signature'] == 'old'
    assert (tmp_path / 'old' / 'report.html').read_text() == 'old complete report'
    assert all(p.name == 'old' or p.name.startswith('.') for p in tmp_path.iterdir())


def test_second_worker_skips_while_report_is_rendering(tmp_path):
    with report_lock(tmp_path) as acquired:
        assert acquired
        assert refresh_report(None, None, root=tmp_path,
            signature=lambda *a, **k: pytest.fail('must not query while locked')) == 'busy'
    with report_lock(tmp_path) as acquired:
        assert acquired


def test_api_supervisor_uses_same_root_and_stops_child_on_shutdown(monkeypatch, tmp_path):
    from backend.app import eda_worker
    started = []

    class Process:
        returncode = None
        async def wait(self):
            if self.returncode is None:
                await asyncio.Event().wait()
            return self.returncode
        def terminate(self):
            self.returncode = -1

    process = Process()
    async def spawn(*args, **kwargs):
        started.append((args, kwargs))
        return process
    monkeypatch.setattr(eda_worker.asyncio, 'create_subprocess_exec', spawn)

    async def check():
        task = asyncio.create_task(eda_worker.refresh_loop(tmp_path))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(check())
    assert '--auto-once' in started[0][0]
    assert str(tmp_path) in started[0][0]
    assert process.returncode == -1
