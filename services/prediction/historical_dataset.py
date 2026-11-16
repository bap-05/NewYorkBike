"""Offline historical bike/weather preparation. Never invent collection times or labels."""
import math

import pandas as pd


def normalize_bikes(frame, *, start, end, known_ids):
    required = ['station_id','num_bikes_available','num_docks_available','is_installed',
        'is_renting','is_returning','last_reported','ts','polled_at']
    if any(c not in frame for c in required):
        raise ValueError('Missing required historical station-status columns')
    data = frame[required].copy()
    if not set(data.station_id.dropna()).issubset(known_ids):
        raise ValueError('Historical file contains an unknown station')
    for field in ('ts','polled_at','last_reported'):
        data[field] = pd.to_datetime(data[field],unit='s',utc=True,errors='coerce')
    # polled_at is when this snapshot was retrieved, not a newly fabricated historical ingestion time.
    data = data.loc[data.polled_at.ge(start) & data.polled_at.lt(end)].copy()
    data['input_time'] = data.polled_at
    age = (data.polled_at-data.last_reported).dt.total_seconds()
    feed_age = (data.polled_at-data.ts).dt.total_seconds()
    data['valid'] = (data.station_id.isin(known_ids) & data.num_bikes_available.ge(0) & data.num_docks_available.ge(0)
        & data.is_installed.eq(1) & data.is_renting.eq(1)
        & age.between(0,600) & feed_age.between(0,600))
    data['slot_utc'] = data.input_time.dt.floor('5min')
    stats = {'rows_in_range':len(data),'invalid_raw_rows':int((~data.valid).sum()),
        'duplicate_station_feed_time':int(data.duplicated(['station_id','ts']).sum())}
    data = data.sort_values(['polled_at','ts']).drop_duplicates(['station_id','slot_utc'],keep='last')
    # Keep invalid markers until lag/target matching; do not bridge an inactive sample with an older valid one.
    stats.update(selected_five_minute_slots=len(data),valid_five_minute_slots=int(data.valid.sum()),
        invalid_five_minute_slots=int((~data.valid).sum()))
    return data.sort_values(['station_id','input_time']).reset_index(drop=True),stats


def join_historical_weather(bikes, weather):
    outputs=[]
    for station, group in bikes.groupby('station_id'):
        right=weather.loc[weather.station_id.eq(station)].drop(columns='station_id').sort_values('weather_time')
        outputs.append(pd.merge_asof(group.sort_values('input_time'),right,
            left_on='input_time',right_on='weather_time',direction='backward',tolerance=pd.Timedelta(hours=1)))
    return pd.concat(outputs,ignore_index=True)


def historical_examples(data):
    outputs=[]
    for station, group in data.groupby('station_id'):
        group=group.sort_values('input_time').copy()
        group['lag_request']=group.input_time-pd.Timedelta(minutes=30)
        group['target_request']=group.input_time+pd.Timedelta(minutes=30)
        lag=group[['input_time','num_bikes_available','valid']].rename(columns={
            'input_time':'lag_time','num_bikes_available':'bikes_lag30','valid':'lag_valid'})
        target=group[['input_time','num_bikes_available','valid','last_reported']].rename(columns={
            'input_time':'actual_time','num_bikes_available':'actual_bikes','valid':'target_valid',
            'last_reported':'target_last_reported'})
        merged=pd.merge_asof(group.sort_values('lag_request'),lag,left_on='lag_request',right_on='lag_time',
            direction='nearest',tolerance=pd.Timedelta(seconds=120))
        merged=pd.merge_asof(merged.sort_values('target_request'),target,left_on='target_request',right_on='actual_time',
            direction='nearest',tolerance=pd.Timedelta(seconds=120))
        valid=(merged.valid & merged.lag_valid.eq(True) & merged.target_valid.eq(True)
            & merged.lag_time.lt(merged.input_time) & merged.actual_time.gt(merged.input_time)
            & merged.target_last_reported.gt(merged.last_reported))
        outputs.append(merged.loc[valid].copy())
    result=pd.concat(outputs,ignore_index=True)
    return result.sort_values(['input_time','station_id']).reset_index(drop=True)


def learning_rows(examples):
    rows=[]
    for r in examples.itertuples():
        local=r.input_time.tz_convert('America/New_York')
        hour=local.hour+local.minute/60
        weather={k:float(getattr(r,k)) for k in ('temperature','humidity','rain','wind_speed')}
        if not all(math.isfinite(v) for v in weather.values()):
            continue
        if not 0<=weather['humidity']<=100 or weather['rain']<0 or weather['wind_speed']<0:
            continue
        rows.append({'station_id':r.station_id,'input_time':r.input_time.to_pydatetime(),
            'label_available_at':r.actual_time.to_pydatetime(),'actual_time':r.actual_time.to_pydatetime(),
            'actual_bikes':int(r.actual_bikes),'baseline':int(r.num_bikes_available),
            'features':{'base':{'station_id':r.station_id,'bikes_now':float(r.num_bikes_available),
                'bikes_lag30':float(r.bikes_lag30),'change30':float(r.num_bikes_available-r.bikes_lag30),
                'hour_sin':math.sin(2*math.pi*hour/24),'hour_cos':math.cos(2*math.pi*hour/24),
                'weekday_sin':math.sin(2*math.pi*local.weekday()/7),'weekday_cos':math.cos(2*math.pi*local.weekday()/7),
                'is_weekend':int(local.weekday()>=5)},'weather':weather}})
    return rows
