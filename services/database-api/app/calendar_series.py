"""Bounded read-only calendar selections; never generate PNGs or call source APIs."""
from datetime import date, datetime, time, timedelta
import re
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select

from backend.app import repositories as repo
from shared.cadence import SamplingCadence, load_sampling_schedule
from shared.config import integer
from shared.models import BikeObservation, Station
from shared.repositories.silver import bike_observations
from shared.time import UTC

ZONE = ZoneInfo('America/New_York')


def calendar_window(period, anchor):
    """Use civil New York boundaries; DST days need not contain 24 hours."""
    try:
        if period == 'day' and re.fullmatch(r'\d{4}-\d{2}-\d{2}', anchor):
            first = date.fromisoformat(anchor)
            last = first + timedelta(days=1)
        elif period == 'week' and re.fullmatch(r'\d{4}-W\d{2}', anchor):
            first = date.fromisocalendar(int(anchor[:4]), int(anchor[-2:]), 1)
            last = first + timedelta(days=7)
        elif period == 'month' and re.fullmatch(r'\d{4}-\d{2}', anchor):
            first = date.fromisoformat(anchor + '-01')
            last = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
        else:
            raise ValueError('Invalid calendar selection')
        return tuple(datetime.combine(d, time.min, ZONE).astimezone(UTC) for d in (first, last))
    except (ValueError, OverflowError):
        raise HTTPException(422, detail='Chọn ngày YYYY-MM-DD, tuần YYYY-Www hoặc tháng YYYY-MM hợp lệ.') from None


def read_series(ctx, source, period, anchor, station_id=None):
    start, end = calendar_window(period, anchor)
    if start >= ctx.now or (end - start).total_seconds() > ctx.options.max_range_days * 86400 + 3600:
        raise HTTPException(422, detail='Kỳ đã chọn chưa bắt đầu hoặc vượt giới hạn truy vấn.')
    cutoff = min(end, ctx.now)
    if station_id:
        stations = [repo.station_or_404(ctx, source, station_id)]
    else:
        stations = list(ctx.session.scalars(select(Station).where(Station.source == source,
            Station.is_monitored.is_(True)).order_by(Station.station_id).limit(101)))
        if len(stations) > 100:
            raise HTTPException(422, detail='Chọn một trạm để thu hẹp truy vấn.')
    ids = [s.station_id for s in stations]
    query = bike_observations(source=source, available_at=ctx.now, include_unusable=True,include_archived=True).where(
        BikeObservation.station_id.in_(ids), BikeObservation.sampled_at >= start,
        BikeObservation.sampled_at < cutoff).order_by(BikeObservation.collected_at, BikeObservation.id).limit(100001)
    rows = list(ctx.session.scalars(query))
    if len(rows) > 100000:
        raise HTTPException(422, detail='Quá nhiều mẫu; chọn một trạm hoặc kỳ ngắn hơn.')
    changes = load_sampling_schedule() if source == ctx.settings.bike_source else ()
    cadence = SamplingCadence(integer('ANALYSIS_EXPECTED_INTERVAL_SECONDS', 1800, 60, 3600), changes)
    latest = {s.station_id: {} for s in stations}
    def priority(sample):
        return (sample.source!='citibike_historical',sample.sampled_at,sample.collected_at,sample.id)
    for row in rows:
        tick=cadence.slot_at(row.sampled_at)
        previous=latest[row.station_id].get(tick)
        if previous is None or priority(row)>priority(previous):
            latest[row.station_id][tick] = row
    items = []
    for station in stations:
        points, previous = [], None
        for tick, row in sorted(latest[station.station_id].items()):
            usable = (row.quality_status == 'valid' and row.is_installed is True
                and row.is_renting is True and row.available_bikes is not None)
            points.append({'at': row.sampled_at, 'value': row.available_bikes if usable else None,
                'gap_before': previous is not None and not cadence.adjacent(previous, tick)})
            previous = tick
        items.append({'station_id': station.station_id, 'name': station.name,
            'capacity': station.capacity, 'points': points})
    return {'source': source, 'period': period, 'anchor': anchor, 'timezone': 'America/New_York',
        'range_start_utc': start, 'range_end_utc': end, 'available_until_utc': cutoff,
        'partial_period': end > ctx.now, 'raw_rows': len(rows), 'items': items}
