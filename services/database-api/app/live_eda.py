"""Bounded, read-only EDA from Silver. No report files, forecasts or model training."""
from dataclasses import replace
from datetime import timedelta
import math
from threading import Lock

import numpy as np
import pandas as pd
from fastapi import HTTPException
from sqlalchemy import select

from analysis.config import AnalysisOptions
from backend.app import repositories as repo
from eda.dataset import load_frame, mark_latest_slots
from eda.patterns import calendar_aggregates
from eda.statistics import daily_coverage, correlation_tables
from shared.cadence import SamplingCadence
from shared.models import Station

MAX_ROWS = 200000
_calculation_lock = Lock()


def json_value(value):
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def records(frame):
    return json_value(frame.to_dict(orient='records'))


def read_chart_data(ctx, source, kind, days, station_id=None):
    # Canceling a browser request does not cancel a synchronous DB calculation.
    # Bound overlapping calculations on small instances instead of multiplying
    # DataFrame memory while a previous chart is still finishing.
    if not _calculation_lock.acquire(blocking=False):
        raise HTTPException(429, 'EDA is busy; retry after the current chart finishes',
            headers={'Retry-After': '3'})
    try:
        return _read_chart_data(ctx, source, kind, days, station_id)
    finally:
        _calculation_lock.release()


def _read_chart_data(ctx, source, kind, days, station_id=None):
    if station_id:
        stations = [repo.station_or_404(ctx, source, station_id)]
    else:
        query = select(Station).where(Station.source == source, Station.is_monitored.is_(True))
        # Match the public station list. STATION_IDS configures collectors and
        # workers; it must not hide monitored stations that already have history.
        stations = list(ctx.session.scalars(query.order_by(Station.station_id).limit(101)))
        if len(stations) > 100:
            raise HTTPException(422, 'Select a station to narrow the query')
    result = dict(source=source, data_source='database', chart=kind,
        range_start_utc=(ctx.now - timedelta(days=days)).isoformat(),
        cutoff_utc=ctx.now.isoformat(), timezone='America/New_York',
        stations=[{'station_id': row.station_id, 'name': row.name} for row in stations],
        raw_rows=0, daily=[], weekly=[], monthly=[], correlation=[],
        decomposition=[], decomposition_status=[])
    if not stations:
        return result
    settings = replace(ctx.settings, bike_source=source, station_ids=tuple(row.station_id for row in stations))
    options = AnalysisOptions.load()
    if source != ctx.settings.bike_source:
        options = replace(options, sampling_schedule=())
    cadence = SamplingCadence(options.expected_interval_seconds, options.sampling_schedule)
    start = ctx.now - timedelta(days=days)
    try:
        frame, stations, firsts = load_frame(ctx.session, settings, options, start, ctx.now,
            MAX_ROWS, include_weather=kind == 'correlation')
    except ValueError as exc:
        if 'row limit exceeded' in str(exc):
            raise HTTPException(422, 'Too many observations; select one station or fewer days') from None
        raise
    frame = mark_latest_slots(frame, cadence)
    result['raw_rows'] = len(frame)
    if kind in ('trend', 'seasonality'):
        coverage = daily_coverage(frame, stations, firsts, cadence, options, start, ctx.now)
        tables = calendar_aggregates(frame, coverage, ctx.now)
        result.update({key: records(table) for key, table in tables.items()})
    elif kind == 'correlation':
        matrix = correlation_tables(frame)['ALL']['correlation']
        result['correlation'] = [{'': str(name), **json_value(row.to_dict())} for name, row in matrix.iterrows()]
    elif kind == 'decomposition':
        from eda.decomposition import decompose
        metadata, components = decompose(frame, stations, cadence, start, ctx.now, options.timezone_name)
        result.update(decomposition=records(components), decomposition_status=json_value(metadata))
    return result
