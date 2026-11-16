"""Opt-in marked estimates for live day-ahead inputs, never scoring targets."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select

from shared.models import BikeObservation, CollectionRun
from shared.time import UTC

ZONE = ZoneInfo('America/New_York')


def load_forecast_estimates(session, stations, start, cutoff):
    rows = []
    query = select(BikeObservation, CollectionRun).join(CollectionRun,
        CollectionRun.id == BikeObservation.collection_run_id).where(
        BikeObservation.source == 'citibike_estimated', CollectionRun.source == 'citibike_estimated',
        BikeObservation.station_id.in_([s.station_id for s in stations]),
        BikeObservation.sampled_at >= start, BikeObservation.sampled_at < cutoff,
        BikeObservation.collected_at <= cutoff, CollectionRun.finished_at <= cutoff,
        CollectionRun.status == 'partial')
    for bike, run in session.execute(query):
        metadata = run.feed_metadata or {}
        if metadata.get('is_estimated') is not True or bike.available_bikes is None or bike.available_bikes < 0:
            continue
        if bike.station_id not in metadata.get('estimates', {}):
            continue
        rows.append({'station_id': bike.station_id, 'sampled_at': bike.sampled_at,
            'bikes': float(bike.available_bikes), 'is_estimated': True})
    return pd.DataFrame(rows, columns=['station_id','sampled_at','bikes','is_estimated'])


def live_forecast_history(base, daily, frame, coverage, estimates, cadence, cutoff):
    """A separate combined input cohort; actual quality/trends are untouched."""
    actual = base.copy()
    actual['is_estimated'] = False
    if estimates is None or estimates.empty:
        return actual, daily
    derived = estimates.copy()
    derived['sampled_at'] = pd.to_datetime(derived.sampled_at, utc=True)
    derived = derived.loc[derived.sampled_at < cutoff].copy()
    occupied = {(r.station_id, cadence.slot_at(r.sampled_at.to_pydatetime()))
        for r in frame.loc[frame.slot_latest].itertuples()}
    derived = derived.loc[[(r.station_id, cadence.slot_at(r.sampled_at.to_pydatetime())) not in occupied
        for r in derived.itertuples()]].copy()
    derived['slot'] = [cadence.slot_at(at.to_pydatetime()) for at in derived.sampled_at]
    derived = derived.drop_duplicates(['station_id','slot'], keep='last')
    derived['local_date'] = derived.sampled_at.dt.tz_convert(ZONE).dt.strftime('%Y-%m-%d')
    derived['local_hour'] = derived.sampled_at.dt.tz_convert(ZONE).dt.hour
    columns = ['station_id','sampled_at','local_date','local_hour','bikes','is_estimated']
    combined = pd.concat([actual[columns], derived[columns]], ignore_index=True)
    hourly = combined.groupby(['station_id','local_date','local_hour']).bikes.mean()
    totals = hourly.groupby(['station_id','local_date']).mean().rename('mean_bikes').reset_index()
    counts = combined.groupby(['station_id','local_date']).bikes.count().rename('input_samples').reset_index()
    totals = totals.merge(counts, on=['station_id','local_date'])
    totals = totals.merge(coverage[['station_id','local_date','partial_day']], on=['station_id','local_date'], how='left')
    def expected(date):
        day = datetime.fromisoformat(date).date()
        begin = datetime.combine(day,time.min,ZONE).astimezone(UTC)
        end = datetime.combine(day+timedelta(days=1),time.min,ZONE).astimezone(UTC)
        return sum(1 for _ in cadence.slots(begin,end))
    expectations = {day:expected(day) for day in totals.local_date.unique()}
    totals['input_coverage'] = totals.input_samples / totals.local_date.map(expectations)
    today = cutoff.astimezone(ZONE).date().isoformat()
    totals['eligible'] = ((totals.input_coverage >= .8) & ~totals.partial_day.fillna(True).astype(bool)
                          & (totals.local_date < today) & totals.mean_bikes.notna())
    return combined, totals
