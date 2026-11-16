"""Marked bike estimates for descriptive statistics; never actual quality or weather."""
from collections import defaultdict
from types import SimpleNamespace

from sqlalchemy import select

from shared.models import BikeObservation, CollectionRun

BIKE_METRICS = {'available_bikes_mean', 'available_bikes_min', 'available_bikes_max',
    'available_bikes_stddev', 'empty_ratio', 'low_bikes_ratio', 'mean_absolute_change'}


def estimated_entries(session, ids, start, cutoff, cadence, pairs):
    occupied = {(b.station_id, cadence.slot_at(b.sampled_at)) for b,*_ in pairs}
    result = defaultdict(list)
    query = select(BikeObservation, CollectionRun).join(CollectionRun,
        CollectionRun.id == BikeObservation.collection_run_id).where(
        BikeObservation.source == 'citibike_estimated', CollectionRun.source == 'citibike_estimated',
        BikeObservation.station_id.in_(ids), BikeObservation.sampled_at >= start,
        BikeObservation.sampled_at < cutoff, BikeObservation.collected_at <= cutoff,
        CollectionRun.finished_at <= cutoff, CollectionRun.status == 'partial').order_by(BikeObservation.id)
    for bike, run in session.execute(query):
        metadata = run.feed_metadata or {}
        method = metadata.get('estimates', {}).get(bike.station_id, {}).get('method')
        slot = (bike.station_id, cadence.slot_at(bike.sampled_at))
        if (metadata.get('is_estimated') is not True or method not in ('linear_interpolation','same_hour_median')
            or bike.available_bikes is None or bike.available_bikes < 0 or slot in occupied):
            continue
        # In-memory calculation adapter only. The stored estimate remains quality=missing.
        proxy = SimpleNamespace(id=bike.id, sampled_at=bike.sampled_at, collected_at=bike.collected_at,
            available_bikes=bike.available_bikes, quality_status='valid', is_installed=True, is_renting=True)
        result[bike.station_id].append((proxy, None, run.finished_at, False))
        occupied.add(slot)
    return result
