"""Refresh completed EDA snapshots without writing to the source database."""
from contextlib import contextmanager
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.database import make_engine
from shared.models import CollectionRun, ObservationWeatherLink, Station, WeatherObservation
from shared.time import utcnow


@contextmanager
def report_lock(root):
    """One generator per report directory, including across API reloads/workers."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.automatic.lock').open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            yield False
            return
        try:
            yield True
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def input_signature(settings, options, *, now, days, max_rows):
    """Use publication time as well as IDs so late historical imports invalidate."""
    engine = make_engine(settings)
    try:
        with Session(engine) as session:
            sources = [settings.bike_source]
            if settings.bike_source == 'citibike':
                sources.append('citibike_historical')
            runs = session.execute(select(func.count(CollectionRun.id),
                func.max(CollectionRun.id), func.max(CollectionRun.finished_at)).where(
                CollectionRun.source.in_(sources),
                CollectionRun.status.in_(['success', 'partial']))).one()
            weather = session.execute(select(func.count(WeatherObservation.id),
                func.max(WeatherObservation.id), func.max(WeatherObservation.collected_at))).one()
            links = session.execute(select(func.count(ObservationWeatherLink.bike_observation_id),
                func.max(ObservationWeatherLink.bike_observation_id),
                func.max(ObservationWeatherLink.weather_observation_id))).one()
            stations = session.execute(select(Station.station_id, Station.name,
                Station.capacity, Station.is_monitored).where(Station.source.in_(sources))
                .order_by(Station.source, Station.station_id)).all()
    finally:
        engine.dispose()
    payload = dict(version=2, source=settings.bike_source, station_ids=settings.station_ids,
        days=days, max_rows=max_rows, options=options.as_dict(),
        local_day=now.astimezone(ZoneInfo(options.timezone_name)).date().isoformat(),
        runs=[str(v) for v in runs], weather=[str(v) for v in weather],
        links=list(links), stations=[list(row) for row in stations])
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def refresh_report(settings, options, *, root, days=28, max_rows=200000,
        clock=utcnow, signature=input_signature, generate=None):
    from eda.main import create_report
    generate = generate or create_report
    root = Path(root).resolve()
    with report_lock(root) as acquired:
        if not acquired:
            return 'busy'
        now = clock()
        fingerprint = signature(settings, options, now=now, days=days, max_rows=max_rows)
        state_path = root / '.automatic.json'
        try:
            previous = json.loads(state_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            previous = {}
        previous_id = previous.get('report_id', '')
        if (previous.get('signature') == fingerprint and previous_id
                and Path(previous_id).name == previous_id
                and (root / previous_id / 'report.html').is_file()
                and (root / previous_id / 'summary.json').is_file()):
            return 'unchanged'
        report_id = now.strftime('%Y%m%dT%H%M%S%fZ')
        # Invalid report ID keeps partially rendered PNGs invisible to the API.
        staging = root / f'.pending-{report_id}'
        generate(settings, options, start=now - timedelta(days=days), cutoff=now,
            output=staging, max_rows=max_rows)
        if not (staging / 'report.html').is_file() or not (staging / 'summary.json').is_file():
            raise RuntimeError('EDA generator did not complete the report')
        staging.rename(root / report_id)
        temporary = root / '.automatic.tmp'
        temporary.write_text(json.dumps(dict(signature=fingerprint, report_id=report_id)), encoding='utf-8')
        temporary.replace(state_path)
        return 'updated'
