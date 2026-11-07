"""Test-only Silver observations; never insert constructed data into production."""
from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from analysis.config import AnalysisOptions
from analysis.statistics import summarize, windows
from analysis import worker
from shared.models import AnalysisResult, BikeObservation, CollectionRun, ObservationWeatherLink, ServiceRun, Station, WeatherObservation
from shared.repositories.gold import analysis_results
from shared.time import UTC

CUTOFF = datetime(2026, 1, 1, 14, tzinfo=UTC)


@pytest.fixture
def analysis_settings(settings, monkeypatch):
    monkeypatch.setattr(worker, "utcnow", lambda: CUTOFF + timedelta(minutes=17))
    return replace(settings, station_ids=("unit-test-only",), mysql_host="unit-test.invalid",
                   mysql_user="unit_test", mysql_database="unit_test", mysql_password="test-only", mysql_ssl_ca=None)


def observation(session, at, count, *, source="citibike", quality="valid", status="success",
                installed=True, renting=True, weather=None, finished_at=None):
    station = session.get(Station, (source, "unit-test-only"))
    if station is None:
        station = Station(source=source, station_id="unit-test-only", name="Unit test only", latitude=40.75,
                          longitude=-73.99, capacity=30, is_monitored=True, updated_at=at)
        session.add(station)
    run = CollectionRun(source=source, scheduled_at=at, started_at=at,
        finished_at=finished_at or at + timedelta(seconds=20), status=status, success_count=1, error_count=0)
    session.add(run)
    session.flush()
    bike = BikeObservation(source=source, station_id=station.station_id, collection_run_id=run.id,
        sampled_at=at, collected_at=at + timedelta(seconds=5), source_observed_at=at,
        available_bikes=count, quality_status=quality, is_installed=installed, is_renting=renting)
    session.add(bike)
    session.flush()
    if weather is True:
        weather = WeatherObservation(source="open-meteo", collection_run_id=run.id,
            requested_latitude=40.75, requested_longitude=-73.99, weather_time=at,
            collected_at=at + timedelta(seconds=10), interval_seconds=900,
            temperature=10, humidity=60, rain=0, wind_speed=2,
            units={"temperature_2m":"\u00b0C","relative_humidity_2m":"%","rain":"mm","wind_speed_10m":"m/s"})
        session.add(weather)
        session.flush()
    if weather is not None:
        session.add(ObservationWeatherLink(bike_observation_id=bike.id, weather_observation_id=weather.id))
    session.commit()
    return bike, weather


def value(session, metric, *, aggregation="day", start=None):
    query = analysis_results().where(AnalysisResult.metric_name == metric, AnalysisResult.aggregation == aggregation)
    if start is not None:
        query = query.where(AnalysisResult.window_start == start)
    return session.scalars(query.order_by(AnalysisResult.window_start.desc())).first()


def analyze(session, settings, *, cutoff=CUTOFF, options=None):
    return worker.analyze_once(session, settings, options or AnalysisOptions(window_days=1), cutoff=cutoff)


def test_actual_statistics_preserve_zero_and_exclude_inactive(session, analysis_settings):
    observation(session, CUTOFF-timedelta(hours=2), 0, weather=True)
    observation(session, CUTOFF-timedelta(minutes=90), 2, weather=True)
    observation(session, CUTOFF-timedelta(hours=1), 20, quality="inactive", renting=False, weather=True)
    observation(session, CUTOFF-timedelta(minutes=30), 10, weather=True)
    result = analyze(session, analysis_settings)
    assert result.status == "success"
    avg = value(session, "available_bikes_mean")
    assert avg.metric_value == 4 and avg.sample_count == 3
    assert avg.expected_sample_count == 4 and avg.coverage == .75
    assert avg.quality_status == "low_coverage"
    assert value(session, "empty_ratio").metric_value == pytest.approx(1/3)
    assert value(session, "low_bikes_ratio").metric_value == pytest.approx(1/3)
    assert value(session, "inactive_ratio").metric_value == .25
    assert value(session, "mean_absolute_change").metric_value == 2


def test_unfinished_failed_future_and_other_source_are_not_read(session, analysis_settings):
    observation(session, CUTOFF-timedelta(hours=2), 4)
    observation(session, CUTOFF-timedelta(minutes=90), 30, status="failed")
    observation(session, CUTOFF-timedelta(hours=1), 30, status="running", finished_at=CUTOFF+timedelta(minutes=1))
    observation(session, CUTOFF-timedelta(minutes=30), 30, finished_at=CUTOFF+timedelta(minutes=1))
    observation(session, CUTOFF-timedelta(minutes=25), 30, source="seoul")
    analyze(session, analysis_settings)
    assert value(session, "available_bikes_mean").metric_value == 4
    assert value(session, "available_bikes_mean").sample_count == 1


def test_missing_weather_never_becomes_zero_or_removes_bikes(session, analysis_settings):
    observation(session, CUTOFF-timedelta(hours=1), 4)
    observation(session, CUTOFF-timedelta(minutes=30), 8)
    analyze(session, analysis_settings)
    assert value(session, "available_bikes_mean").metric_value == 6
    assert value(session, "temperature_mean_c").metric_value is None
    assert value(session, "temperature_mean_c").quality_status == "insufficient_data"
    assert value(session, "missing_weather_ratio").metric_value == 1


def test_reused_weather_is_not_counted_twice_in_weather_mean(session, analysis_settings):
    _, weather = observation(session, CUTOFF-timedelta(hours=1), 4, weather=True)
    weather.rain = 1
    session.commit()
    observation(session, CUTOFF-timedelta(minutes=30), 8, weather=weather)
    analyze(session, analysis_settings)
    assert value(session, "temperature_mean_c").sample_count == 1
    assert value(session, "rain_rate_mean_mm_h").metric_value == 4
    assert value(session, "available_bikes_mean_rain").metric_value == 6
    assert value(session, "missing_weather_ratio").metric_value == 0


@pytest.mark.parametrize("field,value_", [
    ("temperature", None), ("requested_latitude", 41),
    ("collected_at", CUTOFF+timedelta(seconds=1)),
    ("weather_time", CUTOFF+timedelta(seconds=1)),
    ("units", {"wind_speed_10m":"km/h"}),
])
def test_bad_or_unavailable_weather_is_excluded(session, analysis_settings, field, value_):
    _, weather = observation(session, CUTOFF-timedelta(minutes=30), 4, weather=True)
    setattr(weather, field, value_)
    session.commit()
    analyze(session, analysis_settings)
    assert value(session, "temperature_mean_c").metric_value is None
    assert value(session, "available_bikes_mean").metric_value == 4


def test_missing_intervals_have_null_means_and_real_coverage(session, analysis_settings):
    observation(session, CUTOFF-timedelta(hours=3), 4)
    observation(session, CUTOFF-timedelta(minutes=30), 8)
    analyze(session, analysis_settings)
    missing = value(session, "available_bikes_mean", aggregation="hour", start=CUTOFF-timedelta(hours=2))
    assert missing.metric_value is None and missing.sample_count == 0
    assert missing.expected_sample_count == 2 and missing.coverage == 0
    assert value(session, "mean_absolute_change").metric_value is None


def test_multiple_manual_samples_use_latest_observation_in_slot(session, analysis_settings):
    observation(session, CUTOFF-timedelta(minutes=55), 20)
    observation(session, CUTOFF-timedelta(minutes=50), 4)
    observation(session, CUTOFF-timedelta(minutes=20), 8)
    analyze(session, analysis_settings)
    row = value(session, "available_bikes_mean")
    assert row.metric_value == 6 and row.sample_count == 2
    assert row.observed_sample_count == 3 and row.coverage == 1


def test_same_period_is_idempotent_and_unchanged_next_period_skips(session, analysis_settings):
    observation(session, CUTOFF-timedelta(minutes=30), 4)
    first = analyze(session, analysis_settings)
    count = session.scalar(select(func.count()).select_from(AnalysisResult))
    repeated = analyze(session, analysis_settings)
    assert first.id == repeated.id and repeated.attempt_count == 1
    # At :05 a newly due missing slot changes coverage; at :10 nothing else changed.
    second = analyze(session, analysis_settings, cutoff=CUTOFF+timedelta(minutes=5))
    after_boundary = session.scalar(select(func.count()).select_from(AnalysisResult))
    assert after_boundary > count
    third = analyze(session, analysis_settings, cutoff=CUTOFF+timedelta(minutes=10))
    assert third.status == "skipped" and third.result_count == 0
    assert session.scalar(select(func.count()).select_from(AnalysisResult)) == after_boundary


def test_config_changes_keep_separate_results(session, analysis_settings):
    observation(session, CUTOFF-timedelta(minutes=30), 4)
    first = analyze(session, analysis_settings)
    second = analyze(session, analysis_settings, options=AnalysisOptions(window_days=1,low_bike_threshold=5))
    assert first.configuration_hash != second.configuration_hash
    assert session.scalar(select(func.count()).select_from(ServiceRun)) == 2


def test_failed_publication_rolls_back_gold_and_records_safe_failure(session, analysis_settings, monkeypatch):
    observation(session, CUTOFF-timedelta(hours=1), 4)
    first = analyze(session, analysis_settings)
    count = session.scalar(select(func.count()).select_from(AnalysisResult))
    observation(session, CUTOFF-timedelta(minutes=30), 8)
    persist = worker.persist_results
    def fail(session, rows):
        persist(session, rows)
        raise RuntimeError("test-only-secret-uri")
    monkeypatch.setattr(worker, "persist_results", fail)
    # Different config creates a separate publication, avoiding the successful period guard.
    with pytest.raises(RuntimeError):
        analyze(session, analysis_settings, options=AnalysisOptions(window_days=1,low_bike_threshold=5))
    assert session.scalar(select(func.count()).select_from(AnalysisResult)) == count
    failed = session.scalar(select(ServiceRun).where(ServiceRun.status == "failed"))
    assert failed.error_summary == "RuntimeError"
    monkeypatch.setattr(worker, "persist_results", persist)
    retried = analyze(session, analysis_settings, options=AnalysisOptions(window_days=1,low_bike_threshold=5))
    assert retried.id == failed.id and retried.attempt_count == 2 and retried.status == "success"


def test_no_observations_skips_without_fake_statistics(session, analysis_settings):
    result = analyze(session, analysis_settings)
    assert result.status == "skipped" and result.result_count == 0
    assert session.scalars(select(AnalysisResult)).all() == []


@pytest.mark.parametrize("cutoff,hours", [
    ("2026-11-02T05:00:00+00:00",25), ("2026-03-09T04:00:00+00:00",23)])
def test_new_york_dst_days_and_repeated_hours_have_distinct_utc_keys(cutoff, hours):
    # Two local calendar days are requested because cutoff is midnight of the next day.
    result = windows(datetime.fromisoformat(cutoff), AnalysisOptions(window_days=2))
    day = [item for item in result if item[0] == "day"][0]
    assert (day[2]-day[1]).total_seconds() == hours*3600
    hour_keys = [start for aggregation,start,end in result if aggregation == "hour"]
    assert len(hour_keys) == len(set(hour_keys)) == hours


@pytest.mark.parametrize("kwargs", [{"expected_interval_seconds":0},{"expected_interval_seconds":700},
    {"min_coverage":float('nan')},{"min_coverage":1.1},{"window_days":0},{"ingestion_grace_seconds":1800}])
def test_invalid_analysis_options_are_rejected(kwargs):
    with pytest.raises(ValueError):
        AnalysisOptions(**kwargs)
