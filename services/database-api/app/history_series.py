"""Merge explicitly marked historical estimates for display only."""
from sqlalchemy import select

from backend.app import repositories as repo
from shared.cadence import SamplingCadence, load_sampling_schedule
from shared.config import integer
from shared.models import BikeObservation, CollectionRun


def history_with_estimates(ctx, source, station_id, start, end, limit, offset):
    actual = list(ctx.session.scalars(repo.history_query(ctx,source,station_id,start,end)))
    combined = [(b,False,None) for b in actual]
    if source == 'citibike':
        cadence = SamplingCadence(integer('ANALYSIS_EXPECTED_INTERVAL_SECONDS',1800,60,3600),load_sampling_schedule())
        occupied = {cadence.slot_at(b.sampled_at) for b in actual}
        query = select(BikeObservation,CollectionRun.feed_metadata).join(CollectionRun,
            CollectionRun.id==BikeObservation.collection_run_id).where(
            BikeObservation.source=='citibike_estimated',CollectionRun.source=='citibike_estimated',
            BikeObservation.station_id==station_id,BikeObservation.sampled_at>=start,
            BikeObservation.sampled_at<end,BikeObservation.collected_at<=ctx.now,
            CollectionRun.finished_at<=ctx.now,CollectionRun.status=='partial')
        for bike,metadata in ctx.session.execute(query):
            metadata = metadata or {}
            provenance = metadata.get('estimates',{}).get(station_id,{})
            method = provenance.get('method')
            if (metadata.get('is_estimated') is not True or
                method not in ('linear_interpolation','same_hour_median') or
                bike.available_bikes is None or bike.available_bikes<0 or
                cadence.slot_at(bike.sampled_at) in occupied):
                continue
            combined.append((bike,True,method))
            occupied.add(cadence.slot_at(bike.sampled_at))
    combined.sort(key=lambda row:(row[0].sampled_at,row[0].id))
    return combined[offset:offset+limit], {'total':len(combined),'limit':limit,'offset':offset,
        'has_more':offset+limit<len(combined)}
