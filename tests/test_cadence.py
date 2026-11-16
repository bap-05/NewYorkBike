"""Synthetic fixtures stay in isolated unit tests; production is never populated."""
from dataclasses import replace
from datetime import datetime, timedelta
import json
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from analysis.config import AnalysisOptions
from analysis.statistics import summarize
from clustering.config import ClusteringOptions
from clustering.features import calculate_features, bounds
from shared.cadence import SamplingCadence, load_sampling_schedule
from shared.models import BikeObservation, CollectionRun, Station
from shared.time import UTC

CHANGE = '2026-11-09T11:25:00+00:00'
CHANGES = ((CHANGE, 300),)


def dt(value):
    return datetime.fromisoformat(value)


def test_split_hour_and_local_transition_day():
    plan = SamplingCadence(1800, CHANGES)
    slots = list(plan.slots(dt('2026-11-09T11:00:00+00:00'), dt('2026-11-09T12:00:00+00:00')))
    assert [s.minute for s in slots] == [0, 25, 30, 35, 40, 45, 50, 55]
    assert len(list(plan.slots(dt('2026-11-08T05:00:00+00:00'), dt('2026-11-09T05:00:00+00:00')))) == 48
    assert len(list(plan.slots(dt('2026-11-09T05:00:00+00:00'), dt('2026-11-10T05:00:00+00:00')))) == 224
    assert len(list(plan.slots(dt('2026-11-10T05:00:00+00:00'), dt('2026-11-11T05:00:00+00:00')))) == 288


def test_adjacency_does_not_bridge_missing_new_slot():
    plan = SamplingCadence(1800, CHANGES)
    assert plan.adjacent(dt('2026-11-09T11:00:40+00:00'), dt('2026-11-09T11:25:25+00:00'))
    assert plan.adjacent(dt('2026-11-09T11:25:25+00:00'), dt('2026-11-09T11:30:41+00:00'))
    assert not plan.adjacent(dt('2026-11-09T11:25:25+00:00'), dt('2026-11-09T11:35:25+00:00'))


@pytest.mark.parametrize('begin,end,hours', [
    ('2026-03-08T05:00:00+00:00', '2026-03-09T04:00:00+00:00', 23),
    ('2026-11-01T04:00:00+00:00', '2026-11-02T05:00:00+00:00', 25),
])
def test_dst_uses_real_utc_slots(begin, end, hours):
    assert len(list(SamplingCadence(1800).slots(dt(begin), dt(end)))) == hours * 2
    assert len(list(SamplingCadence(300).slots(dt(begin), dt(end)))) == hours * 12


def test_multiple_changes_including_return_to_old_cadence():
    plan = SamplingCadence(1800, CHANGES + (('2026-11-09T12:00:00+00:00', 1800),))
    assert [s.minute for s in plan.slots(dt('2026-11-09T12:00:00+00:00'), dt('2026-11-09T13:00:00+00:00'))] == [0, 30]


@pytest.mark.parametrize('changes', [
    (('2026-11-09T11:25:00', 300),),
    (('2026-11-09T11:25:01+00:00', 300),),
    ((CHANGE, 301),), ((CHANGE, True),),
    CHANGES + CHANGES,
    (('2026-11-09T11:30:00+00:00', 300),) + CHANGES,
])
def test_invalid_or_ambiguous_configuration_fails_closed(changes):
    with pytest.raises(ValueError):
        SamplingCadence(1800, changes)


def test_source_scoped_file_configuration_and_grace(tmp_path, monkeypatch):
    path = tmp_path / 'schedule.json'
    path.write_text(json.dumps({'version': 1, 'sources': {'citibike': [
        {'effective_at': CHANGE, 'interval_seconds': 300}], 'seoul': []}}))
    monkeypatch.setenv('SAMPLING_SCHEDULE_FILE', str(path))
    monkeypatch.setenv('BIKE_SOURCE', 'citibike')
    assert load_sampling_schedule() == CHANGES
    assert AnalysisOptions.load().sampling_schedule == CHANGES
    assert ClusteringOptions.load().sampling_schedule == CHANGES
    monkeypatch.setenv('BIKE_SOURCE', 'seoul')
    assert load_sampling_schedule() == ()
    with pytest.raises(ValueError):
        AnalysisOptions(sampling_schedule=CHANGES, ingestion_grace_seconds=300)


def summarize_hour(*, missing_minute=None, invalidate_minute=None, cutoff=None):
    plan = SamplingCadence(1800, CHANGES)
    start, end = dt('2026-11-09T11:00:00+00:00'), dt('2026-11-09T12:00:00+00:00')
    entries = []
    for i, tick in enumerate(plan.slots(start, end)):
        if tick.minute == missing_minute:
            continue
        at = tick + timedelta(seconds=25)
        bike = SimpleNamespace(id=i, sampled_at=at, collected_at=at, quality_status='valid',
            available_bikes=0, is_installed=True, is_renting=True)
        entries.append((bike, None, at, False))
        if tick.minute == invalidate_minute:
            duplicate = SimpleNamespace(**vars(bike))
            duplicate.id += 100
            duplicate.sampled_at += timedelta(seconds=5)
            duplicate.quality_status = 'inactive'
            duplicate.is_renting = False
            entries.append((duplicate, None, at, False))
    if cutoff:
        entries = [entry for entry in entries if entry[0].sampled_at < cutoff]
    station = SimpleNamespace(source='citibike', station_id='TEST-ONLY')
    results = summarize(entries, station=station, first_observation=start,
        aggregation='hour', start=start, end=end, cutoff=cutoff or end,
        options=AnalysisOptions(sampling_schedule=CHANGES), weather_max_age=900)
    return {row['metric_name']: row for row in results}


def test_analysis_mixed_hour_counts_real_expected_slots_not_legacy_buckets():
    metric = summarize_hour()['available_bikes_mean']
    assert metric['sample_count'] == metric['expected_sample_count'] == 8
    assert metric['coverage'] == 1 and metric['metric_value'] == 0
    missing = summarize_hour(missing_minute=35)
    assert missing['available_bikes_mean']['coverage'] == 7 / 8
    assert missing['missing_slot_ratio']['metric_value'] == 1 / 8


def test_analysis_dedup_invalid_latest_counts_against_quality_not_missing_slot():
    metrics = summarize_hour(invalidate_minute=35)
    assert metrics['available_bikes_mean']['coverage'] == 7 / 8
    assert metrics['available_bikes_mean']['observed_sample_count'] == 9
    assert metrics['missing_slot_ratio']['metric_value'] == 0
    assert metrics['missing_weather_ratio']['metric_value'] == 1


def test_analysis_does_not_expect_future_slots_or_an_unreceived_slot_inside_grace():
    metrics = summarize_hour(cutoff=dt('2026-11-09T11:35:10+00:00'))
    assert metrics['available_bikes_mean']['expected_sample_count'] == 3
    assert metrics['available_bikes_mean']['coverage'] == 1


def test_clustering_mixed_week_and_missing_new_slot(session, settings):
    options = ClusteringOptions(sampling_schedule=CHANGES)
    cutoff = dt('2026-11-10T12:00:00+00:00')
    _, start, end = bounds(cutoff, options)
    plan = SamplingCadence(1800, CHANGES)
    station = Station(source='citibike', station_id='CADENCE-TEST', name='Isolated test only',
        latitude=40.75, longitude=-73.99, capacity=30, is_monitored=True, updated_at=start)
    session.add(station)
    session.flush()
    for tick in plan.slots(start, end):
        run = CollectionRun(source='citibike', scheduled_at=tick, started_at=tick,
            finished_at=tick + timedelta(seconds=25), status='success', success_count=1, error_count=0)
        session.add(run)
        session.flush()
        session.add(BikeObservation(source='citibike', station_id=station.station_id,
            collection_run_id=run.id, sampled_at=tick + timedelta(seconds=10),
            collected_at=tick + timedelta(seconds=15), source_observed_at=tick,
            available_bikes=10, quality_status='valid', is_installed=True, is_renting=True))
    session.commit()
    selected = replace(settings, station_ids=(station.station_id,))
    features, summary = calculate_features(session, selected, options, cutoff)
    assert summary['expected_samples_per_station'] == 512
    assert len(features) == 1 and features[0]['coverage'] == 1
    assert features[0]['daily_coverage']['2026-11-09'] == 1
    row = session.scalar(select_bike_at(dt('2026-11-09T12:35:10+00:00')))
    session.delete(row)
    session.commit()
    features, _ = calculate_features(session, selected, options, cutoff)
    assert features[0]['sample_count'] == 511
    assert features[0]['daily_coverage']['2026-11-09'] == pytest.approx(223 / 224)


def select_bike_at(instant):
    from sqlalchemy import select
    return select(BikeObservation).where(BikeObservation.station_id == 'CADENCE-TEST', BikeObservation.sampled_at == instant)
