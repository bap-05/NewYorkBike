"""Read immutable day-ahead publications and actual scores; no computation on GET."""
from copy import deepcopy

from backend.app.schemas import DayAheadReport
from prediction.day_ahead import daily_period, published_runs, actual_summary


def current_report(ctx, source):
    runs = published_runs(ctx.session, source, ctx.now, days=7)
    current = next((run for run in runs if run.scheduled_at == daily_period(ctx.now)), None)
    if current is None:
        return None
    report = deepcopy(current.summary['report'])
    report.update(publication_id=current.id, persisted=True)
    for station in report['day_ahead']:
        station['issued_evaluation'] = actual_summary(runs, station['station_id'])
    return DayAheadReport.model_validate(report)


def history_report(ctx, source):
    runs = published_runs(ctx.session, source, ctx.now, days=7)
    stations = {}
    for run in runs:
        for station in run.summary['report']['day_ahead']:
            stations.setdefault(station['station_id'], station['station_name'])
    return [{'station_id': station_id, 'station_name': name,
        'issued_evaluation': actual_summary(runs, station_id)} for station_id, name in stations.items()]
