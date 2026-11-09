"""Read-only HTTP contracts with isolated test-only SQLite data."""
from dataclasses import replace
from datetime import datetime, timedelta
import json

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.config import ApiOptions
from backend.app.main import create_app
from shared.models import (AnalysisResult, Base, BikeObservation, ClusteringRun, CollectionRun,
    ModelVersion, ObservationWeatherLink, Prediction, ServiceRun, Station, StationCluster, WeatherObservation)
from shared.time import UTC

NOW=datetime(2026,11,9,7,4,tzinfo=UTC)


@pytest.fixture
def api(settings):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    @event.listens_for(engine,'connect')
    def fk(connection,_):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
        connection.execute(text("INSERT INTO alembic_version VALUES ('0006_prediction')"))
    config=replace(settings,mysql_host='unit-test.invalid',station_ids=())
    app=create_app(settings=config,options=ApiOptions(),engine=engine,clock=lambda:NOW)
    with Session(engine,expire_on_commit=False) as session,TestClient(app,raise_server_exceptions=False) as client:
        yield client,session,app
    engine.dispose()


def station(session,source='citibike',station_id='00001',name='Unit test only'):
    item=session.get(Station,(source,station_id))
    if item is None:
        item=Station(source=source,station_id=station_id,name=name,latitude=40.75,longitude=-73.99,
            capacity=30,is_monitored=True,updated_at=NOW-timedelta(days=1))
        session.add(item)
        session.commit()
    return item


def bike(session,at,number=7,*,source='citibike',station_id='00001',quality='valid',renting=True,status='success',finished=None):
    station(session,source,station_id)
    run=CollectionRun(source=source,scheduled_at=at,started_at=at,
        finished_at=finished or at+timedelta(seconds=20),status=status,success_count=1,error_count=0)
    session.add(run)
    session.flush()
    row=BikeObservation(source=source,station_id=station_id,collection_run_id=run.id,sampled_at=at,
        collected_at=at+timedelta(seconds=5),source_observed_at=at-timedelta(seconds=10),available_bikes=number,
        available_docks=10,quality_status=quality,is_installed=True,is_renting=renting,is_returning=True)
    session.add(row)
    session.commit()
    return row


def control(session,name='prediction',*,source='citibike',at=None,status='success',config='a'*64):
    at=at or NOW-timedelta(minutes=3)
    row=ServiceRun(source=source,service_name=name,scheduled_at=at,started_at=at,
        finished_at=at+timedelta(seconds=10) if status!='running' else None,heartbeat_at=at,
        status=status,attempt_count=1,calculation_version='test-only',configuration_hash=config,
        configuration={},result_count=1)
    session.add(row)
    session.commit()
    return row


def forecast(session,b,*,at=None,status='baseline',run_status='success'):
    at=at or NOW-timedelta(minutes=2)
    run=control(session,at=at,status=run_status,source=b.source)
    model=ModelVersion(source=b.source,name='Test baseline',kind='persistence',identity_hash=str(run.id).zfill(64),
        created_at=at,feature_config={},metrics={},artifact={'secret_test_sentinel':'must-not-be-serialized'},is_active=False)
    session.add(model)
    session.flush()
    row=Prediction(source=b.source,station_id=b.station_id,service_run_id=run.id,scheduled_at=at,
        input_time=b.sampled_at,input_cutoff_at=at,target_at=b.sampled_at+timedelta(minutes=30),issued_at=at,
        input_observation_id=b.id,model_version_id=model.id if status!='unavailable' else None,
        status=status,reason='stale_observation' if status=='unavailable' else 'no_eligible_active_ml_model',
        raw_predicted_bikes=7 if status!='unavailable' else None,predicted_bikes=7 if status!='unavailable' else None,
        features={'internal_test_field':'must-not-be-serialized'})
    session.add(row)
    session.commit()
    return row


def weather(session,b,*,temperature=10,run_id=None):
    row=WeatherObservation(collection_run_id=run_id or b.collection_run_id,requested_latitude=40.75,
        requested_longitude=-73.99,weather_time=b.sampled_at-timedelta(minutes=5),
        collected_at=b.collected_at,temperature=temperature,humidity=60,rain=0,wind_speed=2,
        interval_seconds=900,source='open-meteo',units={
            'temperature_2m':'\u00b0C','relative_humidity_2m':'%','rain':'mm','wind_speed_10m':'km/h'})
    session.add(row)
    session.flush()
    session.add(ObservationWeatherLink(bike_observation_id=b.id,weather_observation_id=row.id))
    session.commit()
    return row


def cluster(session,*,status='success',at=None):
    at=at or NOW-timedelta(hours=3)
    station(session)
    run=control(session,'clustering',at=at,status='success' if status=='success' else 'skipped')
    row=ClusteringRun(source='citibike',run_date=at.date(),service_run_id=run.id,
        window_start=at-timedelta(days=7),window_end=at-timedelta(hours=1),input_cutoff=at,
        started_at=at,finished_at=at+timedelta(seconds=10),status=status,algorithm='test-only',
        calculation_version='test-only',configuration_hash=str(run.id).zfill(64),feature_config={},
        parameters={'selected_k':2,'silhouette':.5} if status=='success' else {'reason':'too_few_eligible_stations'},
        summary={'eligible_stations':6 if status=='success' else 0})
    session.add(row)
    session.flush()
    if status=='success':
        session.add(StationCluster(source='citibike',station_id='00001',clustering_run_id=row.id,cluster_label=0,
            distance_to_centroid=.1,feature_values={'test_feature':.1},metadata_snapshot={'name':'Unit test only'},
            sample_count=300,expected_sample_count=336,coverage=300/336,profile={}))
    session.commit()
    return row


def test_liveness_readiness_docs_and_no_writes(api):
    client,session,_=api
    assert client.get('/health/live').json()=={'status':'ok'}
    assert client.get('/health/ready').status_code==200
    assert client.get('/docs').status_code==200
    schema=client.get('/openapi.json').json()
    assert '/api/stations/{station_id}/history' in schema['paths']
    assert not any(method in ('post','patch','put','delete') for path in schema['paths'].values() for method in path)
    assert session.scalar(select(func.count()).select_from(ServiceRun))==0


def test_source_identity_missing_and_zero_preserved(api):
    client,session,_=api
    bike(session,NOW-timedelta(minutes=4),0)
    bike(session,NOW-timedelta(minutes=3),20,source='seoul')
    station(session,station_id='00002')
    result=client.get('/api/stations').json()
    assert result['pagination']['total']==2
    first=result['items'][0]
    assert first['station_id']=='00001' and first['latest_observation']['available_bikes']==0
    assert first['availability_status']=='fresh'
    assert result['items'][1]['latest_observation'] is None
    assert client.get('/api/stations',params={'source':'seoul'}).json()['items'][0]['latest_observation']['available_bikes']==20


def test_latest_inactive_is_not_hidden_by_old_valid_or_unpublished(api):
    client,session,_=api
    bike(session,NOW-timedelta(minutes=8),8)
    inactive=bike(session,NOW-timedelta(minutes=4),4,quality='inactive',renting=False)
    bike(session,NOW-timedelta(minutes=2),19,status='running')
    bike(session,NOW-timedelta(minutes=1),20,finished=NOW+timedelta(minutes=1))
    result=client.get('/api/stations/00001').json()['item']
    assert result['latest_observation']['id']==inactive.id
    assert result['availability_status']=='inactive'


def test_stale_observation_and_unknown_flags(api):
    client,session,_=api
    row=bike(session,NOW-timedelta(minutes=20),7)
    assert client.get('/api/stations/00001').json()['item']['availability_status']=='stale'
    row.sampled_at=row.collected_at=NOW-timedelta(minutes=2)
    row.source_observed_at=None
    row.is_renting=None
    session.commit()
    assert client.get('/api/stations/00001').json()['item']['availability_status']=='unknown'


def test_partial_weather_and_original_units_preserved(api):
    client,session,_=api
    b=bike(session,NOW-timedelta(minutes=4),7)
    weather(session,b,temperature=None)
    response=client.get('/api/stations/00001').json()['item']['latest_weather']
    assert response['temperature'] is None and response['rain']==0
    assert response['status']=='partial' and response['units']['wind_speed_10m']=='km/h'


def test_unpublished_weather_is_not_exposed(api):
    client,session,_=api
    b=bike(session,NOW-timedelta(minutes=4))
    other=CollectionRun(source='citibike',scheduled_at=NOW-timedelta(minutes=1),started_at=NOW,
        status='running',success_count=0,error_count=0)
    session.add(other)
    session.flush()
    weather(session,b,run_id=other.id)
    assert client.get('/api/stations/00001').json()['item']['latest_weather'] is None


def test_search_literal_wildcards_pagination_and_unknown_station(api):
    client,session,_=api
    station(session,name='100% Test')
    station(session,station_id='00002',name='Avenue Test')
    response=client.get('/api/stations',params={'q':'%','limit':1}).json()
    assert response['pagination']['total']==1
    assert response['items'][0]['name']=='100% Test'
    response=client.get('/api/stations',params={'limit':1,'offset':1}).json()
    assert response['items'][0]['station_id']=='00002'
    assert client.get('/api/stations/not-found').status_code==404
    assert client.get('/api/stations',params={'source':'another-system'}).status_code==422


@pytest.mark.parametrize('params',[{'limit':501},{'limit':0},{'offset':-1}])
def test_pagination_bounds(api,params):
    client,_,_=api
    assert client.get('/api/stations',params=params).status_code==422


@pytest.mark.parametrize('params',[
    {'from':'2026-11-09T00:00:00'},
    {'from':'2026-10-01T00:00:00Z'},
    {'from':'2026-11-09T08:00:00Z'},
    {'to':'2026-11-10T00:00:00Z'},
])
def test_history_requires_bounded_offset_aware_time_range(api,params):
    client,session,_=api
    station(session)
    assert client.get('/api/stations/00001/history',params=params).status_code==422


def test_history_keeps_inactive_and_missing_counts(api):
    client,session,_=api
    bike(session,NOW-timedelta(hours=2),None,quality='missing')
    bike(session,NOW-timedelta(hours=1),4,quality='inactive',renting=False)
    result=client.get('/api/stations/00001/history').json()
    assert result['pagination']['total']==2
    assert result['items'][0]['observation']['available_bikes'] is None
    assert result['items'][1]['observation']['availability_status']=='inactive'


def test_forecast_baseline_label_no_model_artifact_or_features(api):
    client,session,_=api
    b=bike(session,NOW-timedelta(minutes=4),7)
    forecast(session,b)
    response=client.get('/api/stations/00001/predictions/latest')
    result=response.json()
    assert result['status']=='available' and result['item']['status']=='baseline'
    assert result['item']['model']['kind']=='persistence'
    assert 'must-not-be-serialized' not in response.text
    assert 'features' not in result['item'] and 'artifact' not in result['item']['model']


def test_unavailable_latest_does_not_fallback_to_old_baseline(api):
    client,session,_=api
    b=bike(session,NOW-timedelta(minutes=4),7)
    forecast(session,b,at=NOW-timedelta(minutes=3))
    newest=forecast(session,b,at=NOW-timedelta(minutes=1),status='unavailable')
    result=client.get('/api/stations/00001/predictions/latest').json()
    assert result['status']=='unavailable' and result['item']['id']==newest.id
    assert result['item']['predicted_bikes'] is None


def test_prediction_from_running_worker_is_hidden(api):
    client,session,_=api
    b=bike(session,NOW-timedelta(minutes=4),7)
    forecast(session,b,run_status='running')
    assert client.get('/api/stations/00001/predictions/latest').json()['status']=='missing'


def test_prediction_expiration_is_explicit(api):
    client,session,app=api
    b=bike(session,NOW-timedelta(minutes=4),7)
    forecast(session,b)
    app.state.clock=lambda:NOW+timedelta(minutes=40)
    result=client.get('/api/stations/00001/predictions/latest').json()
    assert result['item']['status']=='baseline' and result['item']['display_reason']=='target_passed'
    assert not result['item']['is_current']


def test_fresh_latest_station_does_not_mask_stale_forecast_input(api):
    client,session,_=api
    original=bike(session,NOW-timedelta(minutes=4),7)
    original.source_observed_at=NOW-timedelta(minutes=13)
    session.commit()
    forecast(session,original)
    bike(session,NOW-timedelta(minutes=1),9)
    result=client.get('/api/stations/00001/predictions/latest').json()
    assert not result['item']['is_current']
    assert result['item']['display_reason']=='input_observation_unusable'


def test_future_evaluation_fields_are_not_exposed(api):
    client,session,_=api
    b=bike(session,NOW-timedelta(minutes=4),7)
    p=forecast(session,b)
    p.evaluated_at=NOW+timedelta(minutes=30)
    p.actual_bikes=15
    p.absolute_error=8
    session.commit()
    result=client.get('/api/stations/00001/predictions/latest').json()['item']
    assert result['actual_bikes'] is None and result['evaluated_at'] is None


def test_clusters_insufficient_and_retained_previous_success(api):
    client,session,_=api
    success=cluster(session)
    insufficient=cluster(session,status='insufficient_data',at=NOW-timedelta(hours=1))
    result=client.get('/api/clusters').json()
    assert result['latest_attempt']['id']==insufficient.id
    assert result['latest_success']['id']==success.id
    assert result['status']=='available'
    assert client.get(f'/api/clusters/{insufficient.id}/stations').status_code==409
    members=client.get(f'/api/clusters/{success.id}/stations').json()
    assert members['items'][0]['station_id']=='00001'
    assert client.get(f'/api/clusters/{success.id}/stations',params={'source':'seoul'}).status_code==404


def test_analysis_only_published_one_default_configuration(api):
    client,session,_=api
    station(session)
    for index,status in enumerate(('success','success','running')):
        at=NOW-timedelta(minutes=10-index)
        run=control(session,'analysis',at=at,status=status,config=str(index)*64)
        session.add(AnalysisResult(source='citibike',station_id='00001',window_start=NOW-timedelta(hours=2),
            window_end=NOW-timedelta(hours=1),aggregation='hour',metric_name='available_bikes_mean',
            metric_value=None if index==1 else 7,sample_count=2,observed_sample_count=2,expected_sample_count=2,
            coverage=1,quality_status='insufficient_data' if index==1 else 'ok',dimensions={},
            input_cutoff=at,input_watermark=at,calculated_at=at,calculation_version='test-only',
            configuration_hash=str(index)*64,service_run_id=run.id))
    session.commit()
    result=client.get('/api/analysis').json()
    assert result['configuration_hash']=='1'*64 and len(result['items'])==1
    assert result['items'][0]['metric_value'] is None
    assert client.get('/api/analysis',params={'configuration_hash':'invalid'}).status_code==422


def test_api_session_rejects_write_even_with_same_database_credentials(api):
    client,session,app=api
    from backend.app.routers.common import Context
    @app.get('/test-only-write-attempt')
    def write_attempt(ctx:Context):
        ctx.session.execute(text("INSERT INTO alembic_version VALUES ('test-only-write')"))
        ctx.session.commit()
        return {'unexpected':'write succeeded'}
    response=client.get('/test-only-write-attempt')
    assert response.status_code==503
    assert session.scalar(text("SELECT COUNT(*) FROM alembic_version"))==1


def test_overview_no_fresh_data_does_not_invent_total_zero(api):
    client,session,_=api
    bike(session,NOW-timedelta(minutes=40),7)
    result=client.get('/api/overview').json()
    assert result['fresh_available_bikes'] is None
    assert result['observation_status_counts']=={'stale':1}


def test_cors_explicit_allowlist(api):
    client,_,_=api
    good=client.options('/api/stations',headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'GET'})
    assert good.headers['access-control-allow-origin']=='http://localhost:5173'
    bad=client.get('/health/live',headers={'Origin':'https://untrusted.invalid'})
    assert 'access-control-allow-origin' not in bad.headers


def test_old_schema_returns_503_but_live_stays_up(api):
    client,session,_=api
    session.execute(text("UPDATE alembic_version SET version_num='0005_clustering'"))
    session.commit()
    assert client.get('/health/ready').status_code==503
    assert client.get('/health/live').status_code==200


def test_database_failure_has_no_secret_in_response(api,monkeypatch):
    client,_,app=api
    def broken():
        raise OperationalError('SELECT secret_test_password',{},Exception('do-not-leak'))
    monkeypatch.setattr(app.state.engine,'connect',broken)
    response=client.get('/api/stations')
    assert response.status_code==503
    assert 'secret_test_password' not in response.text and 'do-not-leak' not in response.text
    assert client.get('/health/live').status_code==200


def test_api_does_not_write_or_call_background_services(api,monkeypatch):
    client,session,_=api
    bike(session,NOW-timedelta(minutes=4),7)
    for path in ('ingestion.collector.collect_once','analysis.worker.analyze_once',
            'clustering.worker.cluster_once','prediction.worker.predict_once','prediction.training.train_once'):
        monkeypatch.setattr(path,lambda *a,**k:pytest.fail('API must not start background workers'))
    for path in ('/api/stations','/api/stations/00001','/api/overview','/api/analysis','/api/clusters'):
        assert client.get(path).status_code==200
    assert session.scalar(select(func.count()).select_from(ServiceRun))==0
    assert session.scalar(select(func.count()).select_from(Prediction))==0
    assert client.post('/api/admin/training-jobs',json={}).status_code==404


def test_new_york_dst_offsets_are_preserved(api):
    client,session,app=api
    first=datetime(2026,11,1,5,30,tzinfo=UTC)
    second=datetime(2026,11,1,6,30,tzinfo=UTC)
    bike(session,first,7)
    bike(session,second,8)
    app.state.clock=lambda:datetime(2026,11,1,7,tzinfo=UTC)
    rows=client.get('/api/stations/00001/history').json()['items']
    assert rows[0]['observation']['sampled_at']['local'].endswith('-04:00')
    assert rows[1]['observation']['sampled_at']['local'].endswith('-05:00')
    assert rows[0]['observation']['sampled_at']['utc']!=rows[1]['observation']['sampled_at']['utc']
