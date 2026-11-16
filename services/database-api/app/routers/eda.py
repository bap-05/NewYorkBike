from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import FileResponse

from backend.app.eda_reports import image_path, latest_report, read_report, report_root, child_path
from backend.app.routers.common import Context, Source
from backend.app.schemas import CalendarSeries, EdaResponse, DayAheadResponse
from backend.app.day_ahead import current_report, history_report
from backend.app.calendar_series import read_series

router = APIRouter(prefix='/api/eda', tags=['EDA snapshots'])
ReportId = Annotated[str, Path(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$')]
Filename = Annotated[str, Path(pattern=r'^[a-z_]+\.png$')]


@router.get('', response_model=EdaResponse)
def eda_summary(request: Request, source: Source = 'citibike'):
    item = latest_report(report_root(request.app.state.options), source, request.app.state.clock())
    return {'status': 'available' if item else 'missing', 'item': item}


@router.get('/day-ahead', response_model=DayAheadResponse)
def day_ahead(request: Request, ctx: Context, source: Source = 'citibike'):
    item = current_report(ctx, source)
    return {'status': 'available' if item else 'missing', 'item': item,
        'history': history_report(ctx, source) if item is None else []}


@router.get('/series', response_model=CalendarSeries)
def eda_series(ctx: Context, period: Literal['day', 'week', 'month'],
        anchor: Annotated[str, Query(min_length=7, max_length=10)], source: Source = 'citibike',
        station_id: Annotated[str|None, Query(min_length=1, max_length=128)] = None):
    return read_series(ctx, source, period, anchor, station_id)


@router.get('/reports/{report_id}/figures/{filename}', response_class=FileResponse)
def eda_figure(report_id: ReportId, filename: Filename, request: Request, source: Source = 'citibike'):
    root = report_root(request.app.state.options)
    try:
        item = read_report(root, report_id, source, request.app.state.clock())
        if filename not in {figure.filename for figure in item.figures}:
            raise ValueError('Figure not published')
        path = image_path(child_path(root, report_id), filename)
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(404, detail='EDA figure not found.') from None
    return FileResponse(path, media_type='image/png', headers={
        'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-cache'})
