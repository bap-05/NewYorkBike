"""Read small precomputed JSON results. Never load observations or fit STL here."""
from sqlalchemy import select
from fastapi import HTTPException

from backend.app import repositories as repo
from shared.eda_snapshots import VERSION, SNAPSHOT_SERVICE, WINDOWS, snapshot_key, empty_chart
from shared.models import ServiceRun


def read_chart_data(ctx, source, kind, days, station_id=None):
    if days not in WINDOWS:
        raise HTTPException(422, 'Select 28, 60 or 90 days')
    if station_id:
        repo.station_or_404(ctx, source, station_id)
    if kind == 'decomposition' and not station_id:
        raise HTTPException(422, 'Select a station for decomposition')
    selected_id = station_id if kind in ('correlation', 'decomposition') else None
    payload = ctx.session.scalar(select(ServiceRun.summary).where(
        ServiceRun.service_name == SNAPSHOT_SERVICE, ServiceRun.source == source,
        ServiceRun.calculation_version == VERSION,
        ServiceRun.configuration_hash == snapshot_key(source, kind, days, selected_id),
        ServiceRun.status == 'success', ServiceRun.finished_at.is_not(None),
        ServiceRun.finished_at <= ctx.now, ServiceRun.scheduled_at <= ctx.now)
        .order_by(ServiceRun.finished_at.desc(), ServiceRun.id.desc()).limit(1))
    if payload is None:
        return empty_chart(source, kind)
    payload = dict(payload)
    if station_id and selected_id is None:
        payload['stations'] = [s for s in payload['stations'] if s['station_id'] == station_id]
        for name in ('daily', 'weekly', 'monthly'):
            payload[name] = [row for row in payload[name] if row['station_id'] == station_id]
    return payload
