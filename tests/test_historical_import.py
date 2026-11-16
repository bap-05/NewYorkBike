"""Historical import uses the isolated SQLite fixture, never production credentials."""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from scripts.import_historical_prediction import SOURCE, WEATHER_SOURCE, persist
from shared.models import BikeObservation, CollectionRun, ObservationWeatherLink, Station, WeatherObservation
from shared.time import UTC

AT=datetime(2026,10,1,tzinfo=UTC)
IMPORTED=datetime(2026,11,13,tzinfo=UTC)


def dataset(session):
    station={'station_id':'TEST-HISTORY','name':'Isolated history test','latitude':'40.750000','longitude':'-73.990000'}
    session.add(Station(source='citibike',station_id=station['station_id'],name=station['name'],
        latitude=Decimal(station['latitude']),longitude=Decimal(station['longitude']),capacity=30,
        is_monitored=True,updated_at=IMPORTED))
    session.commit()
    rows=[]
    for i in range(2):
        at=AT+timedelta(minutes=i*5,seconds=20)
        rows.append({'station_id':station['station_id'],'sampled_at':at,'collected_at':at,
            'source_observed_at':at-timedelta(seconds=10),'available_bikes':0 if i==0 else 7,
            'available_docks':12,'is_installed':True,'is_renting':i==0,'is_returning':True,
            'feed_last_updated':at-timedelta(seconds=2),'quality_status':'valid' if i==0 else 'inactive',
            'slot':AT+timedelta(minutes=i*5),'weather_key':(station['station_id'],AT)})
    weather={(station['station_id'],AT):{'source':WEATHER_SOURCE,'weather_time':AT,'collected_at':IMPORTED,
        'requested_latitude':Decimal(station['latitude']),'requested_longitude':Decimal(station['longitude']),
        'temperature':12.,'humidity':60.,'rain':0.,'wind_speed':2.,'units':{'wind_speed_10m':'m/s'},
        'interval_seconds':3600,'collection_run_id':None}}
    return rows,weather,[station]


def test_import_preserves_historical_times_quality_provenance_and_is_idempotent(session):
    rows,weather,stations=dataset(session)
    result=persist(session,rows,weather,stations,'a'*64,{'dataset_path':'isolated-test'},IMPORTED)
    session.commit()
    assert result['inserted_bikes']==2 and result['inserted_weather']==1 and result['inserted_links']==2
    assert session.scalar(select(func.count()).select_from(BikeObservation).where(BikeObservation.source=='citibike'))==0
    observations=list(session.scalars(select(BikeObservation).order_by(BikeObservation.sampled_at)))
    assert observations[0].available_bikes==0 and observations[0].sampled_at==rows[0]['sampled_at']
    assert observations[0].collected_at==rows[0]['collected_at']
    assert observations[1].quality_status=='inactive' and observations[1].is_renting is False
    assert session.get(Station,(SOURCE,stations[0]['station_id'])).capacity is None
    assert session.get(Station,(SOURCE,stations[0]['station_id'])).is_monitored is False
    runs=list(session.scalars(select(CollectionRun).order_by(CollectionRun.scheduled_at)))
    assert [r.status for r in runs]==['success','partial']
    assert all(r.started_at==IMPORTED and r.feed_metadata['is_historical'] for r in runs)
    assert session.scalar(select(WeatherObservation)).collected_at==IMPORTED
    again=persist(session,rows,weather,stations,'a'*64,{'dataset_path':'isolated-test'},IMPORTED)
    assert again['inserted_bikes']==0 and again['skipped_existing']==2
    assert session.scalar(select(func.count()).select_from(BikeObservation))==2
    rows[0]['available_bikes']=99
    with pytest.raises(ValueError,match='refusing to overwrite'):
        persist(session,rows,weather,stations,'a'*64,{},IMPORTED)
    session.rollback()
    assert session.scalar(select(BikeObservation).order_by(BikeObservation.sampled_at)).available_bikes==0


def test_failed_transaction_leaves_no_partial_import_and_conflicting_dataset_is_rejected(session):
    rows,weather,stations=dataset(session)
    broken=dict(weather)
    broken[(stations[0]['station_id'],AT)]={**next(iter(weather.values())),'rain':-1}
    with pytest.raises(IntegrityError):
        persist(session,rows,broken,stations,'b'*64,{},IMPORTED)
    session.rollback()
    assert session.scalar(select(func.count()).select_from(BikeObservation))==0
    assert session.scalar(select(func.count()).select_from(CollectionRun))==0
    assert session.get(Station,(SOURCE,stations[0]['station_id'])) is None
    persist(session,rows,weather,stations,'b'*64,{},IMPORTED)
    session.commit()
    with pytest.raises(ValueError,match='different historical dataset'):
        persist(session,rows,weather,stations,'c'*64,{},IMPORTED)
