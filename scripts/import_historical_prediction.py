"""Import a prepared historical dataset under a separate source, atomically and idempotently."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path

import pandas as pd
from sqlalchemy import event, func, insert, select, text, update
from sqlalchemy.orm import Session

from prediction.historical_dataset import join_historical_weather
from shared.config import Settings
from shared.database import make_engine
from shared.models import BikeObservation, CollectionRun, ObservationWeatherLink, Station, WeatherObservation
from shared.time import as_utc, utcnow

SOURCE='citibike_historical'
WEATHER_SOURCE='open-meteo-era5'
BIKE_FIELDS=('station_id','sampled_at','collected_at','source_observed_at','available_bikes',
    'available_docks','is_installed','is_renting','is_returning','feed_last_updated','quality_status')


def dt(value):
    return None if pd.isna(value) else as_utc(value.to_pydatetime() if hasattr(value,'to_pydatetime') else value)


def count(value):
    return None if pd.isna(value) or value<0 else int(value)


def flag(value):
    return bool(value) if not pd.isna(value) and value in (0,1) else None


def prepare(root):
    report=json.loads((root/'report.json').read_text(encoding='utf-8'))
    files=['report.json','clean_bikes.parquet','rejected_bike_slots.parquet','weather_hourly.parquet']
    hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}
    bikes=pd.concat([pd.read_parquet(root/'clean_bikes.parquet'),pd.read_parquet(root/'rejected_bike_slots.parquet')],ignore_index=True)
    weather=pd.read_parquet(root/'weather_hourly.parquet')
    joined=join_historical_weather(bikes,weather)
    if joined.duplicated(['station_id','input_time']).any():
        raise ValueError('Duplicate station/time in historical input')
    records=[]
    for r in joined.itertuples():
        at=dt(r.input_time)
        quality='valid'
        if not r.valid:
            if (count(r.num_bikes_available) is None or count(r.num_docks_available) is None
                or dt(r.last_reported) is None or dt(r.ts) is None
                or r.last_reported>r.polled_at or r.ts>r.polled_at):
                quality='invalid'
            elif r.is_installed!=1 or r.is_renting!=1:
                quality='inactive'
            else:
                quality='stale'
        if pd.isna(r.weather_time) or not pd.Timedelta(0)<=r.input_time-r.weather_time<=pd.Timedelta(hours=1):
            raise ValueError('Historical weather join is missing or outside its allowed interval')
        records.append({'station_id':r.station_id,'sampled_at':at,'collected_at':dt(r.polled_at),
            'source_observed_at':dt(r.last_reported),'available_bikes':count(r.num_bikes_available),
            'available_docks':count(r.num_docks_available),'is_installed':flag(r.is_installed),
            'is_renting':flag(r.is_renting),'is_returning':flag(r.is_returning),'feed_last_updated':dt(r.ts),
            'quality_status':quality,'slot':dt(r.slot_utc),'weather_key':(r.station_id,dt(r.weather_time))})
    used={r['weather_key'] for r in records}
    weather_rows={}
    cache_store={}
    stations={s['station_id']:s for s in report['stations']}
    for r in weather.itertuples():
        key=(r.station_id,dt(r.weather_time))
        if key not in used:
            continue
        if r.weather_cache_file not in cache_store:
            cache_path=root.parent/'weather_cache'/r.weather_cache_file
            if cache_path.resolve().parent!=(root.parent/'weather_cache').resolve():
                raise ValueError('Invalid weather cache path')
            raw_cache=cache_path.read_bytes()
            cache_store[r.weather_cache_file]=json.loads(raw_cache.decode('utf-8'))
            hashes['weather_cache/'+r.weather_cache_file]=hashlib.sha256(raw_cache).hexdigest()
        saved=cache_store[r.weather_cache_file]
        station=stations[r.station_id]
        values=[float(r.temperature),float(r.humidity),float(r.rain),float(r.wind_speed)]
        if not all(math.isfinite(v) for v in values) or not 0<=values[1]<=100 or min(values[2:])<0:
            raise ValueError('Invalid historical weather values')
        weather_rows[key]={'requested_latitude':Decimal(station['latitude']),'requested_longitude':Decimal(station['longitude']),
            'returned_latitude':Decimal(str(saved['payload']['latitude'])),
            'returned_longitude':Decimal(str(saved['payload']['longitude'])),
            'weather_time':key[1],'collected_at':as_utc(datetime.fromisoformat(r.weather_retrieved_at)),
            'temperature':values[0],'humidity':values[1],'rain':values[2],'wind_speed':values[3],
            'units':{'temperature_2m':'\u00b0C','relative_humidity_2m':'%','rain':'mm','wind_speed_10m':'m/s'},
            'temperature_unit':'\u00b0C','humidity_unit':'%','rain_unit':'mm','wind_speed_unit':'m/s',
            'interval_seconds':3600,'source':WEATHER_SOURCE,'collection_run_id':None}
    digest=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    return records,weather_rows,list(stations.values()),digest,{'dataset_path':str(root.resolve()),
        'files':hashes,'original_inputs':report['inputs'],'weather_product':report['weather_policy']}


def chunks(rows,size=500):
    for offset in range(0,len(rows),size):
        yield rows[offset:offset+size]


def persist(session,records,weather_rows,stations,digest,provenance,now):
    """Caller owns the transaction. Existing observations are never overwritten."""
    by_slot=defaultdict(list)
    for r in records:
        by_slot[r['slot']].append(r)
    slots=sorted(by_slot)
    if not slots:
        raise ValueError('No historical observations to import')
    first,last=slots[0],slots[-1]
    runs=list(session.scalars(select(CollectionRun).where(CollectionRun.source==SOURCE,
        CollectionRun.scheduled_at>=first,CollectionRun.scheduled_at<=last)))
    if any((r.feed_metadata or {}).get('dataset_sha256')!=digest for r in runs):
        raise ValueError('A different historical dataset already overlaps this range')
    old={(b.station_id,b.sampled_at):b for b in session.scalars(select(BikeObservation).where(
        BikeObservation.source==SOURCE,BikeObservation.sampled_at>=min(r['sampled_at'] for r in records),
        BikeObservation.sampled_at<=max(r['sampled_at'] for r in records)))}
    if runs or old:
        if len(runs)!=len(slots) or len(old)!=len(records) or any(r.status not in ('success','partial') for r in runs):
            raise ValueError('Historical import is incomplete; refusing to overwrite existing data')
        for row in records:
            previous=old.get((row['station_id'],row['sampled_at']))
            if previous is None or any(getattr(previous,k)!=row[k] for k in BIKE_FIELDS):
                raise ValueError('Stored historical values differ; refusing to overwrite')
        links=session.scalar(select(func.count()).select_from(ObservationWeatherLink).where(
            ObservationWeatherLink.bike_observation_id.in_(select(BikeObservation.id).where(
                BikeObservation.source==SOURCE,BikeObservation.sampled_at>=min(r['sampled_at'] for r in records),
                BikeObservation.sampled_at<=max(r['sampled_at'] for r in records)))))
        if links!=len(records):
            raise ValueError('Historical weather links are incomplete')
        return {'inserted_bikes':0,'inserted_runs':0,'inserted_weather':0,'inserted_links':0,'skipped_existing':len(records)}
    for s in stations:
        if session.get(Station,('citibike',s['station_id'])) is None:
            raise ValueError('Historical station does not match a current Citi Bike station')
        if session.get(Station,(SOURCE,s['station_id'])) is None:
            # Capacity is not supplied by the historical archive; do not label today's capacity as historical.
            session.add(Station(source=SOURCE,station_id=s['station_id'],name=s['name'],latitude=Decimal(s['latitude']),
                longitude=Decimal(s['longitude']),capacity=None,is_monitored=False,updated_at=now))
    session.flush()
    run_rows=[]
    for slot,group in sorted(by_slot.items()):
        valid=sum(r['quality_status']=='valid' for r in group)
        metadata={'is_historical':True,'is_estimated':False,'dataset_sha256':digest,
            'original_source':'citibike','imported_at':now.isoformat(),
            'original_polled_at_field':'bike_observations.collected_at',
            'weather_product':'ERA5 retrospective reanalysis','dataset_path':provenance.get('dataset_path')}
        if slot==first:
            metadata['dataset_manifest']=provenance
        run_rows.append({'source':SOURCE,'scheduled_at':slot,'started_at':now,'finished_at':None,
            'status':'running','success_count':valid,'error_count':len(group)-valid,'attempt_count':1,
            'feed_metadata':metadata})
    for batch in chunks(run_rows,200):
        session.execute(insert(CollectionRun),batch)
    run_ids=dict(session.execute(select(CollectionRun.scheduled_at,CollectionRun.id).where(
        CollectionRun.source==SOURCE,CollectionRun.scheduled_at>=first,CollectionRun.scheduled_at<=last)).all())
    print('Historical run markers prepared: '+str(len(run_ids)),flush=True)
    # Archived weather has its own source and actual retrieval time, not fabricated historical availability.
    existing_weather=list(session.scalars(select(WeatherObservation).where(WeatherObservation.source==WEATHER_SOURCE,
        WeatherObservation.weather_time>=min(k[1] for k in weather_rows),
        WeatherObservation.weather_time<=max(k[1] for k in weather_rows))))
    def weather_identity(row):
        return (row['requested_latitude'],row['requested_longitude'],row['weather_time'])
    old_weather={(w.requested_latitude,w.requested_longitude,w.weather_time):w for w in existing_weather}
    weather_pending={}
    for row in weather_rows.values():
        identity=weather_identity(row)
        previous=old_weather.get(identity)
        if previous is not None and any(getattr(previous,k)!=row[k] for k in ('temperature','humidity','rain','wind_speed','interval_seconds')):
            raise ValueError('Different ERA5 values already exist for a historical location/hour')
        if previous is None:
            weather_pending[identity]=row
    for batch in chunks(list(weather_pending.values())):
        session.execute(insert(WeatherObservation),batch)
    weather_ids={(w.requested_latitude,w.requested_longitude,w.weather_time):w.id for w in session.scalars(
        select(WeatherObservation).where(WeatherObservation.source==WEATHER_SOURCE,
        WeatherObservation.weather_time>=min(k[1] for k in weather_rows),
        WeatherObservation.weather_time<=max(k[1] for k in weather_rows)))}
    rows=[{**{k:r[k] for k in BIKE_FIELDS},'source':SOURCE,'collection_run_id':run_ids[r['slot']],
        'gbfs_version':None} for r in records]
    inserted=0
    for batch in chunks(rows,1000):
        session.execute(insert(BikeObservation),batch)
        inserted+=len(batch)
        if inserted%10000==0:
            print('Historical bikes prepared: '+str(inserted),flush=True)
    bikes={(sid,at):oid for sid,at,oid in session.execute(select(BikeObservation.station_id,
        BikeObservation.sampled_at,BikeObservation.id).where(BikeObservation.source==SOURCE,
        BikeObservation.sampled_at>=min(r['sampled_at'] for r in records),
        BikeObservation.sampled_at<=max(r['sampled_at'] for r in records)))}
    links=[{'bike_observation_id':bikes[(r['station_id'],r['sampled_at'])],
        'weather_observation_id':weather_ids[weather_identity(weather_rows[r['weather_key']])]} for r in records]
    linked=0
    for batch in chunks(links,1000):
        session.execute(insert(ObservationWeatherLink),batch)
        linked+=len(batch)
        if linked%20000==0:
            print('Historical weather links prepared: '+str(linked),flush=True)
    finished=utcnow()
    for status in ('success','partial'):
        ids=[run_ids[slot] for slot,group in by_slot.items()
            if (all(r['quality_status']=='valid' for r in group))==(status=='success')]
        for batch in chunks(ids,200):
            session.execute(update(CollectionRun).where(CollectionRun.id.in_(batch),
                CollectionRun.source==SOURCE,CollectionRun.status=='running')
                .values(status=status,finished_at=finished).execution_options(synchronize_session=False))
    print('Historical publication markers prepared',flush=True)
    return {'inserted_bikes':len(rows),'inserted_runs':len(run_ids),'inserted_weather':len(weather_pending),
        'inserted_links':len(links),'skipped_existing':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    records,weather,stations,digest,provenance=prepare(Path(args.dataset).resolve())
    summary={'source':SOURCE,'dataset_sha256':digest,'bike_rows':len(records),
        'quality_counts':dict(Counter(r['quality_status'] for r in records)),
        'weather_rows':len(weather),'station_count':len(stations),'database_written':False}
    print(json.dumps(summary),flush=True)
    if not args.apply:
        return
    settings=Settings.load(outbound=False)
    engine=make_engine(settings)
    @event.listens_for(engine,'do_connect')
    def import_timeouts(dialect,connection_record,args,parameters):
        parameters['read_timeout']=120
        parameters['write_timeout']=120
    now=utcnow()
    lock='historical_import_'+hashlib.sha256(str(engine.url.database).encode()).hexdigest()[:24]
    try:
        with engine.connect() as connection:
            acquired=connection.scalar(text('SELECT GET_LOCK(:name,0)'),{'name':lock})
            connection.commit()
            if acquired!=1:
                raise RuntimeError('Another historical import is running')
            try:
                with Session(bind=connection) as session:
                    result=persist(session,records,weather,stations,digest,provenance,now)
                    session.commit()
                    summary.update(result,database_written=True,imported_at=now.isoformat())
            finally:
                connection.rollback()
                connection.execute(text('SELECT RELEASE_LOCK(:name)'),{'name':lock})
                connection.commit()
    finally:
        engine.dispose()
    folder=Path('artifacts/data_imports');folder.mkdir(parents=True,exist_ok=True)
    receipt=folder/(now.strftime('%Y%m%dT%H%M%SZ')+'-'+digest[:12]+'.json')
    receipt.write_text(json.dumps({**summary,'provenance':provenance},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({**summary,'receipt':str(receipt)}),flush=True)


if __name__=='__main__':
    main()
