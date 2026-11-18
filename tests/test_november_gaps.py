"""Real archives fill only unoccupied valid slots and preserve existing samples."""
from datetime import timedelta

import pandas as pd
from sqlalchemy import select

from scripts.import_november_gaps import persist, plan
from shared.models import BikeObservation, CollectionRun, Station
from shared.repositories.silver import bike_observations
from tests.test_historical_import import dataset, IMPORTED


def test_main_gap_fill_is_idempotent_preserves_existing_and_rolls_back(session):
    records, _, _ = dataset(session)
    frame = pd.DataFrame([dict(station_id=r['station_id'],input_time=pd.Timestamp(r['sampled_at']),
        polled_at=pd.Timestamp(r['sampled_at']),last_reported=pd.Timestamp(r['source_observed_at']),
        ts=pd.Timestamp(r['feed_last_updated']),num_bikes_available=r['available_bikes'],
        num_docks_available=r['available_docks'],is_installed=1,is_renting=1,is_returning=1,valid=True)
        for r in records])
    manifest={'sha256':'test','path':'isolated-test'}
    persist(session,frame.iloc[:1],manifest,IMPORTED)
    session.commit()
    assert len(list(session.scalars(bike_observations(source='citibike'))))==1
    original = session.scalar(select(BikeObservation))
    pending = plan(frame,list(session.scalars(select(BikeObservation))))
    assert len(pending)==1
    # Different timestamps inside an occupied five-minute slot are still duplicates.
    shifted=frame.iloc[:1].copy()
    shifted['input_time']+=timedelta(seconds=20)
    assert len(plan(shifted,[original]))==0
    persist(session,pending,manifest,IMPORTED)
    session.flush()
    assert len(plan(frame,list(session.scalars(select(BikeObservation)))))==0
    assert original.available_bikes==0 and original.source=='citibike'
    assert all(r.feed_metadata['is_estimated'] is False for r in session.scalars(select(CollectionRun)))
    session.rollback()
    assert len(list(session.scalars(select(BikeObservation))))==1
    # Invalid archive points are never promoted into valid main observations.
    frame['valid']=False
    assert len(plan(frame,[]))==0


def test_gap_fill_reuses_existing_run_without_changing_original_metadata(session):
    records, _, _ = dataset(session)
    record = records[0]
    frame = pd.DataFrame([dict(station_id=record['station_id'],
        input_time=pd.Timestamp(record['sampled_at']), polled_at=pd.Timestamp(record['sampled_at']),
        last_reported=pd.Timestamp(record['source_observed_at']), ts=pd.Timestamp(record['feed_last_updated']),
        num_bikes_available=record['available_bikes'], num_docks_available=record['available_docks'],
        is_installed=1, is_renting=1, is_returning=1, valid=True)])
    manifest = {'sha256':'first', 'path':'isolated-test'}
    persist(session, frame, manifest, IMPORTED)
    session.commit()
    original_run = session.scalar(select(CollectionRun))
    metadata = dict(original_run.feed_metadata)
    station = session.scalar(select(Station).where(Station.source == 'citibike'))
    session.add(Station(source='citibike', station_id='SECOND', name='Second station',
        latitude=station.latitude, longitude=station.longitude, capacity=30,
        is_monitored=True, updated_at=IMPORTED))
    session.commit()
    frame['station_id'] = 'SECOND'
    persist(session, frame, {'sha256':'second', 'path':'second-file'}, IMPORTED)
    session.flush()
    assert len(list(session.scalars(select(CollectionRun)))) == 1
    assert len(list(session.scalars(select(BikeObservation)))) == 2
    assert original_run.feed_metadata == metadata
    assert all(b.collection_run_id == original_run.id for b in session.scalars(select(BikeObservation)))
