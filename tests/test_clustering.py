"""Constructed unit-test data stays in isolated SQLite, never in Aiven."""
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from clustering.algorithm import fit_clusters
from clustering.config import ClusteringOptions
from clustering.features import FEATURE_NAMES, bounds, calculate_features
from clustering.main import next_daily_run
from clustering import worker
from shared.models import BikeObservation, ClusteringRun, CollectionRun, ServiceRun, Station, StationCluster
from shared.repositories.gold import latest_clustering_run, station_clusters
from shared.time import UTC

CUTOFF = datetime(2026, 1, 10, 16, tzinfo=UTC)


@pytest.fixture
def cluster_settings(settings, monkeypatch):
    monkeypatch.setattr(worker, "utcnow", lambda: CUTOFF + timedelta(hours=1))
    return replace(settings, station_ids=())


def populate(session, *, source="citibike", station_count=6, days=7, options=None):
    options = options or ClusteringOptions()
    _, start, end = bounds(CUTOFF, options)
    stations = []
    for index in range(station_count):
        station = Station(source=source, station_id=f"TEST-{index}", name="Unit test only",
            latitude=40.75, longitude=-73.99, capacity=30, is_monitored=True, updated_at=start)
        session.add(station)
        stations.append(station)
    session.flush()
    tick, number = end-timedelta(days=days), 0
    while tick < end:
        run = CollectionRun(source=source, scheduled_at=tick, started_at=tick,
            finished_at=tick+timedelta(seconds=20), status="success", success_count=station_count, error_count=0)
        session.add(run)
        session.flush()
        for index, station in enumerate(stations):
            # Two separated groups with three stations each, solely for algorithm tests.
            count = (2 if index < 3 else 23) + (number % 3) + index % 3
            session.add(BikeObservation(source=source, station_id=station.station_id, collection_run_id=run.id,
                sampled_at=tick, collected_at=tick+timedelta(seconds=5), source_observed_at=tick,
                available_bikes=count, quality_status="valid", is_installed=True, is_renting=True))
        tick += timedelta(seconds=options.expected_interval_seconds)
        number += 1
    session.commit()
    return stations


def test_complete_history_fit_and_immutable_idempotent_snapshot(session, cluster_settings):
    populate(session)
    options = ClusteringOptions()
    run = worker.cluster_once(session, cluster_settings, options, cutoff=CUTOFF)
    assert run.status == "success"
    assert run.parameters["selected_k"] == 2
    assert run.parameters["silhouette"] > 0
    assert len(run.parameters["scaler_mean"]) == len(FEATURE_NAMES)
    memberships = list(session.scalars(station_clusters()))
    assert len(memberships) == 6
    assert len({m.cluster_label for m in memberships[:3]}) == 1
    assert memberships[0].cluster_label != memberships[-1].cluster_label
    assert all(m.sample_count == 336 and m.coverage == 1 for m in memberships)
    repeat = worker.cluster_once(session, cluster_settings, options, cutoff=CUTOFF+timedelta(minutes=10))
    assert repeat.id == run.id
    assert session.scalar(select(func.count()).select_from(StationCluster)) == 6
    assert session.get(ServiceRun, run.service_run_id).attempt_count == 1
    assert session.scalar(latest_clustering_run(available_at=CUTOFF)) is None  # publication was later


def test_incomplete_history_reports_reasons_and_no_members(session, cluster_settings):
    populate(session, days=4)
    run = worker.cluster_once(session, cluster_settings, ClusteringOptions(), cutoff=CUTOFF)
    assert run.status == "insufficient_data"
    assert run.summary["eligible_stations"] == 0
    assert all("incomplete_daily_coverage" in s["reasons"] for s in run.summary["rejected_stations"])
    assert not list(session.scalars(station_clusters()))
    assert session.get(ServiceRun, run.service_run_id).status == "skipped"
    again = worker.cluster_once(session, cluster_settings, ClusteringOptions(), cutoff=CUTOFF)
    assert again.id == run.id and session.get(ServiceRun, run.service_run_id).attempt_count == 2


def test_quality_slot_dedup_missing_counts_and_source_isolation(session, cluster_settings):
    populate(session, station_count=1)
    populate(session, source="seoul", station_count=1)
    first = session.scalar(select(BikeObservation).where(BikeObservation.source == "citibike").order_by(BikeObservation.sampled_at))
    first.available_bikes = None
    first.quality_status = "missing"
    second = session.scalars(select(BikeObservation).where(BikeObservation.source == "citibike").order_by(BikeObservation.sampled_at)).all()[1]
    second.is_renting, second.quality_status = False, "inactive"
    # Later inactive reading in the same slot must not resurrect the earlier valid sample.
    third = session.scalars(select(BikeObservation).where(BikeObservation.source == "citibike").order_by(BikeObservation.sampled_at)).all()[2]
    session.add(BikeObservation(source="citibike", station_id=third.station_id, collection_run_id=third.collection_run_id,
        sampled_at=third.sampled_at+timedelta(minutes=2), collected_at=third.collected_at+timedelta(minutes=2),
        source_observed_at=third.source_observed_at, available_bikes=0, quality_status="inactive", is_installed=True, is_renting=False))
    fourth = session.scalars(select(BikeObservation).where(BikeObservation.source == "citibike").order_by(BikeObservation.sampled_at)).all()[4]
    fourth.available_bikes = 31  # Never clamp to capacity.
    session.commit()
    features, summary = calculate_features(session, cluster_settings, ClusteringOptions(), CUTOFF)
    assert summary["station_count"] == 1 and len(features) == 1
    assert features[0]["sample_count"] == 332
    assert features[0]["feature_values"]["empty_ratio"] == 0
    assert features[0]["excluded_samples"]["inactive"] == 2
    assert features[0]["raw_statistics"]["max_bikes"] <= 30


def test_unfinished_and_late_publication_are_not_read(session, cluster_settings):
    populate(session, station_count=1)
    runs = session.scalars(select(CollectionRun).order_by(CollectionRun.id)).all()
    runs[0].status, runs[0].finished_at = "running", None
    runs[1].finished_at = CUTOFF + timedelta(hours=1)
    session.commit()
    features, summary = calculate_features(session, cluster_settings, ClusteringOptions(), CUTOFF)
    assert summary["input_rows"] == 334
    assert features[0]["sample_count"] == 334


def test_missing_capacity_rejects_station_without_rack_fallback(session, cluster_settings):
    stations = populate(session, station_count=1)
    stations[0].capacity, stations[0].rack_count = None, 30
    session.commit()
    features, summary = calculate_features(session, cluster_settings, ClusteringOptions(), CUTOFF)
    assert not features
    assert "missing_positive_capacity" in summary["rejected_stations"][0]["reasons"]


def test_atomic_rollback_and_previous_success_remains_visible(session, cluster_settings, monkeypatch):
    populate(session)
    options = ClusteringOptions()
    good = worker.cluster_once(session, cluster_settings, options, cutoff=CUTOFF)
    original = worker.calculate
    def fail(*args):
        members, parameters, summary = original(*args)
        members[1]["station_id"] = members[0]["station_id"]  # duplicate PK forces rollback on flush
        return members, parameters, summary
    monkeypatch.setattr(worker, "calculate", fail)
    with pytest.raises(Exception):
        worker.cluster_once(session, cluster_settings, replace(options, low_bike_threshold=4), cutoff=CUTOFF)
    assert session.scalar(select(func.count()).select_from(StationCluster)) == 6
    assert session.scalar(latest_clustering_run()).id == good.id
    assert len(list(session.scalars(select(ClusteringRun).where(ClusteringRun.status == "failed")))) == 1


def test_constant_features_do_not_invent_groups():
    features = [{"feature_values": dict.fromkeys(FEATURE_NAMES, .5)} for _ in range(6)]
    members, parameters = fit_clusters(features, ClusteringOptions())
    assert not members and parameters["status"] == "insufficient_data"


def test_latest_success_survives_new_insufficient_run(session, cluster_settings):
    populate(session)
    options = ClusteringOptions()
    good = worker.cluster_once(session, cluster_settings, options, cutoff=CUTOFF)
    newer = worker.cluster_once(session, cluster_settings, replace(options, min_samples=1000), cutoff=CUTOFF)
    assert newer.status == "insufficient_data"
    assert session.scalar(latest_clustering_run()).id == good.id
    assert not list(session.scalars(station_clusters(configuration_hash=newer.configuration_hash)))


def test_clustering_is_reproducible(session, cluster_settings):
    populate(session)
    options = ClusteringOptions()
    features, _ = calculate_features(session, cluster_settings, options, CUTOFF)
    left, parameters = fit_clusters(features, options)
    right, repeated = fit_clusters(features, options)
    assert parameters == repeated
    assert [m["cluster_label"] for m in left] == [m["cluster_label"] for m in right]
    assert len(parameters["candidates"]) >= 2


@pytest.mark.parametrize("instant,expected", [
    ("2026-03-08T05:00:00+00:00", "2026-03-08T07:00:00+00:00"),
    ("2026-03-08T07:00:00+00:00", "2026-03-09T06:00:00+00:00"),
    ("2026-11-01T05:30:00+00:00", "2026-11-01T07:00:00+00:00"),
    ("2026-11-01T06:30:00+00:00", "2026-11-01T07:00:00+00:00"),
    ("2026-11-01T07:00:00+00:00", "2026-11-02T07:00:00+00:00"),
])
def test_daily_schedule_dst(instant, expected):
    assert next_daily_run(datetime.fromisoformat(instant)) == datetime.fromisoformat(expected)


@pytest.mark.parametrize("instant,hours", [("2026-03-09T12:00:00+00:00",167), ("2026-11-02T12:00:00+00:00",169)])
def test_seven_local_days_are_not_always_168_hours(instant, hours):
    _, start, end = bounds(datetime.fromisoformat(instant), ClusteringOptions())
    assert (end-start).total_seconds() == hours*3600


def test_reject_future_and_naive_cutoffs(session, cluster_settings):
    with pytest.raises(ValueError, match="future"):
        worker.cluster_once(session, cluster_settings, ClusteringOptions(), cutoff=CUTOFF+timedelta(days=1))
    with pytest.raises(ValueError):
        worker.cluster_once(session, cluster_settings, ClusteringOptions(), cutoff=CUTOFF.replace(tzinfo=None))
