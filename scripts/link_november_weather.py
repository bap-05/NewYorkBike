"""Attach archived hourly weather to the November main-table gap import."""
from collections import Counter
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path

import pandas as pd
from sqlalchemy import event, insert, select

from scripts.import_historical_prediction import chunks
from shared.config import Settings
from shared.database import ingestion_session, make_engine
from shared.models import BikeObservation, CollectionRun, ObservationWeatherLink, Station, WeatherObservation
from shared.time import as_utc, utcnow

ROOT = Path('artifacts/november_weather')
FIELDS = ('temperature','humidity','rain','wind_speed')


def weather_values(row, station, cache):
    params=cache['request']
    if Decimal(str(params['latitude']))!=station.latitude or Decimal(str(params['longitude']))!=station.longitude:
        raise ValueError('Weather cache location does not match station')
    expected={'temperature_2m':'\u00b0C','relative_humidity_2m':'%','rain':'mm','wind_speed_10m':'m/s'}
    if any(cache['payload'].get('hourly_units',{}).get(k)!=v for k,v in expected.items()):
        raise ValueError('Unexpected historical weather units')
    values = {k:float(getattr(row,k)) for k in FIELDS}
    if not all(math.isfinite(v) for v in values.values()):
        return None
    if not 0<=values['humidity']<=100 or values['rain']<0 or values['wind_speed']<0:
        raise ValueError('Historical weather outside valid physical ranges')
    payload=cache['payload']
    if cache['endpoint']=='https://archive-api.open-meteo.com/v1/archive' and params.get('models')=='era5':
        source='open-meteo-era5'
    elif cache['endpoint']=='https://historical-forecast-api.open-meteo.com/v1/forecast' and params.get('models')=='ecmwf_ifs':
        source='open-meteo-historical-forecast'
    else:
        raise ValueError('Unsupported historical weather product')
    return dict(source=source,requested_latitude=station.latitude,requested_longitude=station.longitude,
        returned_latitude=Decimal(str(payload['latitude'])),returned_longitude=Decimal(str(payload['longitude'])),
        weather_time=row.weather_time.to_pydatetime(),collected_at=as_utc(pd.Timestamp(cache['retrieved_at']).to_pydatetime()),
        collection_run_id=None,**values,interval_seconds=3600,
        temperature_unit='\u00b0C',humidity_unit='%',rain_unit='mm',wind_speed_unit='m/s',
        units={'temperature_2m':'\u00b0C','relative_humidity_2m':'%','rain':'mm','wind_speed_10m':'m/s'})


def main():
    weather=pd.read_parquet(ROOT/'hourly.parquet')
    engine=make_engine(Settings.load(outbound=False))
    @event.listens_for(engine,'do_connect')
    def timeouts(dialect,connection,cargs,params):
        params.update(read_timeout=180,write_timeout=180)
    receipt=ROOT/('receipt-'+utcnow().strftime('%Y%m%dT%H%M%SZ')+'.json')
    with ingestion_session(engine) as session:
        stations={s.station_id:s for s in session.scalars(select(Station).where(Station.source=='citibike'))}
        bikes=list(session.scalars(select(BikeObservation).join(CollectionRun).where(
            BikeObservation.source=='citibike',CollectionRun.feed_metadata['import_type'].as_string()=='november_archive_gap_fill')))
        if not bikes:
            raise ValueError('No November imported observations found')
        ids=[b.id for b in bikes]
        old_links={}
        for batch in chunks(ids,1000):
            old_links.update(session.execute(select(ObservationWeatherLink.bike_observation_id,
                ObservationWeatherLink.weather_observation_id).where(ObservationWeatherLink.bike_observation_id.in_(batch))).all())
        pending=[b for b in bikes if b.id not in old_links]
        used={(b.station_id,pd.Timestamp(b.collected_at).floor('h').to_pydatetime()) for b in pending}
        rows={}; station_keys={}; caches={}
        for r in weather.itertuples():
            key=(r.station_id,r.weather_time.to_pydatetime())
            if key not in used:
                continue
            path=ROOT/'cache'/r.weather_cache_file
            if path.resolve().parent!=(ROOT/'cache').resolve():
                raise ValueError('Invalid weather cache path')
            if path.name not in caches:
                raw=path.read_bytes()
                caches[path.name]=(json.loads(raw),hashlib.sha256(raw).hexdigest())
            values=weather_values(r,stations[r.station_id],caches[path.name][0])
            if values is None:
                continue
            identity=(values['source'],values['requested_latitude'],values['requested_longitude'],values['weather_time'])
            rows[identity]=values
            station_keys[key]=identity
        missing=[key for key in used if key not in station_keys]
        if missing:
            raise ValueError(f'Missing {len(missing)} required weather station/hour pairs; no writes performed')
        existing={}
        if rows:
            times=[key[3] for key in rows]
            for w in session.scalars(select(WeatherObservation).where(WeatherObservation.weather_time>=min(times),
                WeatherObservation.weather_time<=max(times),WeatherObservation.source.in_(sorted({key[0] for key in rows})))):
                existing[(w.source,w.requested_latitude,w.requested_longitude,w.weather_time)]=w
        new=[]
        for key,values in rows.items():
            previous=existing.get(key)
            if previous is None:
                new.append(values)
            elif any(not math.isclose(getattr(previous,k),values[k],rel_tol=1e-10,abs_tol=1e-10) for k in FIELDS):
                raise ValueError('Existing weather differs; refusing overwrite')
        for batch in chunks(new,500):
            session.execute(insert(WeatherObservation),batch)
        if rows:
            for w in session.scalars(select(WeatherObservation).where(WeatherObservation.weather_time>=min(times),
                WeatherObservation.weather_time<=max(times),WeatherObservation.source.in_(sorted({key[0] for key in rows})))):
                existing[(w.source,w.requested_latitude,w.requested_longitude,w.weather_time)]=w
        links=[dict(bike_observation_id=b.id,weather_observation_id=existing[station_keys[
            (b.station_id,pd.Timestamp(b.collected_at).floor('h').to_pydatetime())]].id) for b in pending]
        audit={'imported_bikes':len(bikes),'already_linked':len(old_links),'inserted_weather':len(new),
            'inserted_links':len(links),'sources':dict(Counter(v['source'] for v in rows.values())),
            'cache_sha256':{name:pair[1] for name,pair in caches.items()},
            'join':'UTC hour floor, no future interpolation; hourly rain accumulation',
            'retrieved_at_preserved':True,'committed':False}
        for batch in chunks(links,1000):
            session.execute(insert(ObservationWeatherLink),batch)
        session.flush()
        linked={}
        for batch in chunks(ids,1000):
            linked.update(session.execute(select(ObservationWeatherLink.bike_observation_id,
                ObservationWeatherLink.weather_observation_id).where(ObservationWeatherLink.bike_observation_id.in_(batch))).all())
        if len(linked)!=len(bikes) or any(linked.get(k)!=v for k,v in old_links.items()):
            raise RuntimeError('Weather link preservation/count verification failed')
        receipt.with_suffix('.prepared.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
        session.commit()
        audit['committed']=True
        receipt.write_text(json.dumps(audit,indent=2),encoding='utf-8')
        print(json.dumps(audit,indent=2),flush=True)
        print('Receipt:',receipt,flush=True)
    engine.dispose()


if __name__=='__main__':
    main()
