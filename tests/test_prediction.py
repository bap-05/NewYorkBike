"""Constructed fixtures stay in isolated SQLite; no simulated production forecasts."""
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from prediction.config import PredictionOptions
from prediction.data import load_history, training_examples
from prediction.learning import build_report, encoded_features, fit_forest, infer, split_by_time
from prediction import main, training, worker
from prediction.registry import feature_policy
from shared.models import BikeObservation, CollectionRun, ModelVersion, ObservationWeatherLink, Prediction, ServiceRun, Station, TrainingJob, WeatherObservation
from shared.repositories.gold import predictions
from shared.time import UTC, sampling_slot

NOW = datetime(2026,1,16,12,4,tzinfo=UTC)


@pytest.fixture
def prediction_settings(settings,monkeypatch):
    monkeypatch.setattr(worker,"utcnow",lambda:NOW)
    monkeypatch.setattr(training,"utcnow",lambda:NOW)
    return replace(settings,station_ids=("TEST-PREDICTION",))


def add_sample(session,at,count,*,source="citibike",status="success",quality="valid",renting=True,
        weather=True,finished=None,station_id="TEST-PREDICTION"):
    station = session.get(Station,(source,station_id))
    if station is None:
        station=Station(source=source,station_id=station_id,name="Unit test only",latitude=40.75,longitude=-73.99,
            capacity=30,is_monitored=True,updated_at=at)
        session.add(station)
    run=CollectionRun(source=source,scheduled_at=at,started_at=at,finished_at=finished or at+timedelta(seconds=40),
        status=status,success_count=1,error_count=0)
    session.add(run)
    session.flush()
    b=BikeObservation(source=source,station_id=station_id,collection_run_id=run.id,sampled_at=at,
        collected_at=at+timedelta(seconds=5),source_observed_at=at-timedelta(seconds=10),
        available_bikes=count,quality_status=quality,is_installed=True,is_renting=renting)
    session.add(b)
    session.flush()
    if weather:
        w=WeatherObservation(source="open-meteo",collection_run_id=run.id,requested_latitude=40.75,
            requested_longitude=-73.99,weather_time=at-timedelta(minutes=5),collected_at=at+timedelta(seconds=20),
            temperature=10,humidity=60,rain=0,wind_speed=2,interval_seconds=900,
            units={"temperature_2m":"\u00b0C","relative_humidity_2m":"%","rain":"mm","wind_speed_10m":"m/s"})
        session.add(w)
        session.flush()
        session.add(ObservationWeatherLink(bike_observation_id=b.id,weather_observation_id=w.id))
    session.commit()
    return b


def history(session,days=14):
    end=NOW.replace(minute=0)
    at=end-timedelta(days=days)
    index=0
    while at<=end:
        add_sample(session,at,3 if index%2==0 else 19)
        at+=timedelta(minutes=30)
        index+=1


def test_baseline_real_target_utc_and_idempotent_period(session,prediction_settings):
    at=NOW-timedelta(minutes=4)
    b=add_sample(session,at,7,weather=False)
    run=worker.predict_once(session,prediction_settings,PredictionOptions())
    assert run.status=="success"
    p=session.scalar(predictions())
    assert p.status=="baseline" and p.predicted_bikes==7
    assert p.input_time==at and p.target_at==at+timedelta(minutes=30)
    assert p.issued_at==NOW and p.input_observation_id==b.id
    assert session.get(ModelVersion,p.model_version_id).kind=="persistence"
    repeated=worker.predict_once(session,prediction_settings,PredictionOptions())
    assert repeated.id==run.id
    assert session.scalar(select(func.count()).select_from(Prediction))==1


@pytest.mark.parametrize("case,reason",[("inactive","inactive"),("missing","invalid_observation"),
    ("stale","stale_observation"),("capacity","count_exceeds_current_capacity")])
def test_no_forecast_for_invalid_latest_sample(session,prediction_settings,case,reason):
    add_sample(session,NOW-timedelta(minutes=8),7)
    at=NOW-timedelta(minutes=2)
    b=add_sample(session,at,None if case=="missing" else 31 if case=="capacity" else 2,
        quality="inactive" if case=="inactive" else "missing" if case=="missing" else "valid",renting=case!="inactive")
    if case=="stale":
        b.source_observed_at=NOW-timedelta(minutes=11)
        # Source was valid at collection but has aged since; use an older valid sample time.
        b.sampled_at=b.collected_at=NOW-timedelta(minutes=11)
        previous=session.scalar(select(BikeObservation).where(BikeObservation.id!=b.id))
        previous.sampled_at=previous.collected_at=NOW-timedelta(minutes=12)
        previous.source_observed_at=previous.sampled_at
    session.commit()
    worker.predict_once(session,prediction_settings,PredictionOptions())
    p=session.scalar(predictions())
    assert p.status=="unavailable" and p.reason==reason
    assert p.predicted_bikes is None and p.raw_predicted_bikes is None


def test_source_separation_and_unpublished_or_future_input(session,prediction_settings):
    add_sample(session,NOW-timedelta(minutes=4),7)
    add_sample(session,NOW-timedelta(minutes=2),20,source="seoul")
    add_sample(session,NOW-timedelta(minutes=1),23,status="running")
    add_sample(session,NOW-timedelta(seconds=30),24,finished=NOW+timedelta(minutes=1))
    worker.predict_once(session,prediction_settings,PredictionOptions())
    assert session.scalar(predictions()).predicted_bikes==7


def test_no_row_shift_label_across_missing_half_hour(session,prediction_settings):
    at=NOW-timedelta(hours=3)
    a=add_sample(session,at,4)
    add_sample(session,at+timedelta(hours=1),9)
    add_sample(session,at+timedelta(hours=1,minutes=30),10)
    stations,groups=load_history(session,prediction_settings,NOW,PredictionOptions())
    rows,excluded=training_examples(stations,groups,prediction_settings,PredictionOptions())
    assert a.id not in [r["input_observation_id"] for r in rows]
    assert excluded["missing_or_unusable_target"]>=1
    assert len(rows)==1


def test_label_tolerance_is_explicit(session,prediction_settings):
    at=NOW-timedelta(hours=2)
    add_sample(session,at,4)
    add_sample(session,at+timedelta(minutes=31),6)
    options=PredictionOptions()
    stations,groups=load_history(session,prediction_settings,NOW,options)
    rows,_=training_examples(stations,groups,prediction_settings,options)
    assert len(rows)==1 and rows[0]["target_offset_seconds"]==60
    assert rows[0]["actual_time"]!=rows[0]["target_at"]


def test_future_or_wrong_unit_weather_is_not_imputed(session,prediction_settings):
    at=NOW-timedelta(hours=2)
    for index in range(4):
        add_sample(session,at+timedelta(minutes=30*index),4+index)
    weather=session.scalar(select(WeatherObservation).order_by(WeatherObservation.id.desc()))
    weather.units={**weather.units,"wind_speed_10m":"km/h"}
    # The input before this label also has future weather, known only after its feature cutoff.
    older=session.scalars(select(WeatherObservation).order_by(WeatherObservation.id)).all()[1]
    older.collected_at=NOW+timedelta(hours=1)
    session.commit()
    options=PredictionOptions()
    stations,groups=load_history(session,prediction_settings,NOW,options)
    rows,_=training_examples(stations,groups,prediction_settings,options)
    assert rows[1]["features"]["weather"] is None


def test_temporal_split_purges_labels_at_boundaries():
    rows=[]
    for index in range(100):
        at=NOW-timedelta(hours=100-index)
        rows.append({"input_time":at,"label_available_at":at+timedelta(minutes=30)})
    train,val,test,split=split_by_time(rows)
    assert max(r["label_available_at"] for r in train)<min(r["input_time"] for r in val)
    assert max(r["label_available_at"] for r in val)<min(r["input_time"] for r in test)
    assert len(test)==15


def test_insufficient_training_does_not_create_ml_model(session,prediction_settings):
    add_sample(session,NOW-timedelta(minutes=4),7)
    job=training.train_once(session,prediction_settings,PredictionOptions())
    assert job.status=="insufficient_data"
    assert job.model_version_id is None
    assert session.scalar(select(func.count()).select_from(ModelVersion))==0


def test_train_forest_roundtrip_activation_and_live_ml(session,prediction_settings):
    history(session)
    options=PredictionOptions(min_training_samples=100,min_station_samples=50,min_holdout_samples=20)
    job=training.train_once(session,prediction_settings,options)
    assert job.status=="success",job.summary
    model=session.get(ModelVersion,job.model_version_id)
    assert model.is_active and model.metrics["selected"]["test"]["mae"]<1
    artifact=json.loads(json.dumps(model.artifact))
    stations,groups=load_history(session,prediction_settings,NOW,options)
    features=worker.feature_values(groups[stations[0].station_id][-1],groups[stations[0].station_id],stations[0],prediction_settings,options)
    value=infer(artifact,features,stations[0].station_id)
    assert 0<=value<=30
    # Make model available just before this prediction run, rather than exactly at training completion.
    model.created_at=NOW-timedelta(seconds=1)
    session.commit()
    worker.predict_once(session,prediction_settings,options)
    forecast=session.scalar(predictions())
    assert forecast.status=="ml" and forecast.model_version_id==model.id
    assert forecast.raw_predicted_bikes==pytest.approx(value)


def test_json_tree_matches_sklearn_inference():
    import numpy as np
    from sklearn.ensemble import RandomForestRegressor
    rows=[{"station_id":"T","actual_bikes":i%7,"features":{"base":{"station_id":"T","bikes_now":i/10},"weather":None}} for i in range(40)]
    artifact=fit_forest(rows,with_weather=False,depth=4)
    values=[encoded_features(r["features"],False) for r in rows]
    matrix=np.array([[v[n] for n in artifact["feature_names"]] for v in values],dtype=np.float32)
    forest=RandomForestRegressor(n_estimators=40,max_depth=4,min_samples_leaf=5,random_state=42,n_jobs=1)
    forest.fit(matrix,[r["actual_bikes"] for r in rows])
    assert [infer(artifact,r["features"],"T") for r in rows]==pytest.approx(forest.predict(matrix).tolist())


def test_matured_forecast_evaluated_only_after_actual_is_published(session,prediction_settings,monkeypatch):
    at=NOW-timedelta(minutes=4)
    add_sample(session,at,7)
    worker.predict_once(session,prediction_settings,PredictionOptions())
    p=session.scalar(predictions())
    future=at+timedelta(minutes=31)
    actual=add_sample(session,future,9)
    monkeypatch.setattr(worker,"utcnow",lambda:future+timedelta(minutes=3))
    worker.predict_once(session,prediction_settings,PredictionOptions())
    session.refresh(p)
    assert p.actual_observation_id==actual.id
    assert p.target_offset_seconds==60
    assert p.absolute_error==2 and p.squared_error==4
    assert p.predicted_bikes==7  # Issued forecast was not rewritten after observing the answer.


def test_evaluation_keeps_original_tolerance_after_config_changes(session,prediction_settings,monkeypatch):
    at=NOW-timedelta(minutes=4)
    add_sample(session,at,7)
    worker.predict_once(session,prediction_settings,PredictionOptions(timestamp_tolerance_seconds=30))
    p=session.scalar(predictions())
    actual_at=at+timedelta(minutes=31)
    add_sample(session,actual_at,9)
    monkeypatch.setattr(worker,'utcnow',lambda:actual_at+timedelta(minutes=3))
    worker.predict_once(session,prediction_settings,PredictionOptions(timestamp_tolerance_seconds=120))
    session.refresh(p)
    assert p.actual_observation_id is None  # Cannot silently widen the original +/-30-second policy.


def test_failed_publication_rolls_back_forecasts(session,prediction_settings,monkeypatch):
    add_sample(session,NOW-timedelta(minutes=4),7)
    def fail(*args):
        raise RuntimeError("unit test only")
    monkeypatch.setattr(worker,"evaluate_pending",fail)
    with pytest.raises(RuntimeError):
        worker.predict_once(session,prediction_settings,PredictionOptions())
    assert session.scalar(select(func.count()).select_from(Prediction))==0
    assert session.scalar(select(ServiceRun)).status=="failed"


def test_preview_never_writes_database(session,prediction_settings,monkeypatch,tmp_path):
    add_sample(session,NOW-timedelta(minutes=4),7)
    engine=session.get_bind()
    monkeypatch.setattr(main,"make_engine",lambda _:engine)
    monkeypatch.setattr(engine,"dispose",lambda:None)
    monkeypatch.setattr(main,"utcnow",lambda:NOW)
    output=tmp_path/'preview.json'
    assert main.preview(prediction_settings,PredictionOptions(),output=output)==0
    report=json.loads(output.read_text())
    assert report['database_written'] is False
    assert session.scalar(select(func.count()).select_from(Prediction))==0
    assert session.scalar(select(func.count()).select_from(ServiceRun))==0
    assert session.scalar(select(func.count()).select_from(ModelVersion))==0


@pytest.mark.parametrize('value,served',[(-2,0),(99,30)])
def test_raw_ml_score_retained_and_served_clipping_explicit(session,prediction_settings,value,served):
    at=NOW-timedelta(minutes=4)
    add_sample(session,at-timedelta(minutes=30),4)
    add_sample(session,at,7)
    stations,groups=load_history(session,prediction_settings,NOW,PredictionOptions())
    artifact={'format':'citibike-rf-json-v1','station_ids':['TEST-PREDICTION'],'with_weather':False,
        'feature_names':['bikes_now'],'trees':[{'left':[-1],'right':[-1],'feature':[-2],'threshold':[-2.0],'value':[value]}]}
    model=SimpleNamespace(id=123,artifact=artifact)
    row=worker.forecast_rows(stations,groups,prediction_settings,PredictionOptions(),NOW,model)[0]
    assert row['status']=='ml' and row['raw_predicted_bikes']==value and row['predicted_bikes']==served


def test_new_insufficient_training_keeps_previous_active_model(session,prediction_settings):
    model=ModelVersion(source='citibike',name='Unit test only',kind='random_forest',identity_hash='a'*64,
        created_at=NOW-timedelta(days=1),feature_config={},metrics={},artifact={},is_active=True)
    session.add(model)
    session.commit()
    add_sample(session,NOW-timedelta(minutes=4),7)
    job=training.train_once(session,prediction_settings,PredictionOptions())
    assert job.status=='insufficient_data' and model.is_active


def test_missing_lag_falls_back_to_labeled_baseline(session,prediction_settings):
    add_sample(session,NOW-timedelta(minutes=4),7,weather=False)
    stations,groups=load_history(session,prediction_settings,NOW,PredictionOptions())
    model=SimpleNamespace(id=123,artifact={'with_weather':True})
    row=worker.forecast_rows(stations,groups,prediction_settings,PredictionOptions(),NOW,model)[0]
    assert row['status']=='baseline' and row['reason']=='missing_lag30' and row['predicted_bikes']==7


def test_schedule_runs_separately_without_training(monkeypatch,prediction_settings):
    clock=[NOW]
    calls=[]
    class Engine:
        def dispose(self):
            pass
    @contextmanager
    def service(_,name):
        assert name=='prediction'
        yield object()
    def predict(*args):
        calls.append(clock[0])
        if len(calls)==2:
            raise KeyboardInterrupt()
        return SimpleNamespace(id=1,status='success',summary={})
    monkeypatch.setattr(main,'make_engine',lambda _:Engine())
    monkeypatch.setattr(main,'service_session',service)
    monkeypatch.setattr(main,'predict_once',predict)
    monkeypatch.setattr(main,'train_once',lambda *a:pytest.fail('Prediction scheduler must never train'))
    monkeypatch.setattr(main,'utcnow',lambda:clock[0])
    monkeypatch.setattr(main.time,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+timedelta(seconds=seconds)))
    with pytest.raises(KeyboardInterrupt):
        main.run(prediction_settings,PredictionOptions(),schedule=True)
    assert calls==[NOW,sampling_slot(NOW)+timedelta(minutes=5)]


@pytest.mark.parametrize("instant",["2026-03-08T06:59:00+00:00","2026-11-01T05:59:00+00:00","2026-11-01T06:59:00+00:00"])
def test_scheduler_has_distinct_utc_periods_across_dst(instant):
    first=sampling_slot(datetime.fromisoformat(instant))
    second=sampling_slot(first+timedelta(minutes=5))
    assert (second-first).total_seconds()==300
