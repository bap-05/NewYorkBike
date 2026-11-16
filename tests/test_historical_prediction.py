"""Offline historical preparation: no network or production database access."""
import pandas as pd

from prediction.historical_dataset import normalize_bikes, historical_examples, join_historical_weather, learning_rows


def raw_frame():
    start=pd.Timestamp('2026-10-01T04:00:00Z')
    times=[int((start+pd.Timedelta(minutes=5*i)).timestamp()) for i in range(13)]
    return pd.DataFrame({'station_id':['A']*13,'num_bikes_available':list(range(13)),
        'num_docks_available':[20]*13,'is_installed':[1]*13,'is_renting':[1]*13,
        'is_returning':[1]*13,'last_reported':[t-10 for t in times],'ts':times,'polled_at':times})


def normalize(frame):
    return normalize_bikes(frame,start=pd.Timestamp('2026-10-01',tz='UTC'),
        end=pd.Timestamp('2026-10-02',tz='UTC'),known_ids={'A'})


def test_actual_targets_and_lags_are_matched_without_filling_or_bridging_invalid_markers():
    raw=raw_frame()
    data,audit=normalize(raw)
    assert audit['valid_five_minute_slots']==13
    rows=historical_examples(data)
    assert len(rows)==1
    row=rows.iloc[0]
    assert row.num_bikes_available==6 and row.bikes_lag30==0 and row.actual_bikes==12
    assert row.actual_time-row.input_time==pd.Timedelta(minutes=30)
    # An inactive target remains a marker; an older valid target must not replace it.
    raw.loc[12,'is_renting']=0
    invalid,_=normalize(raw)
    assert historical_examples(invalid).empty
    raw.loc[12,'is_renting']=1
    raw.loc[0,'last_reported']=raw.loc[0,'polled_at']+1
    future,_=normalize(raw)
    assert not future.iloc[0].valid
    assert historical_examples(future).empty


def test_weather_join_never_uses_future_hour_and_missing_weather_excludes_training_example():
    data,_=normalize(raw_frame())
    weather=pd.DataFrame({'station_id':['A','A'],
        'weather_time':pd.to_datetime(['2026-10-01T04:00:00Z','2026-10-01T05:00:00Z']),
        'temperature':[10,99],'humidity':[60,60],'rain':[0,4],'wind_speed':[2,2]})
    joined=join_historical_weather(data,weather)
    rows=learning_rows(historical_examples(joined))
    assert len(rows)==1
    assert rows[0]['features']['weather']['temperature']==10
    assert rows[0]['features']['weather']['rain']==0
    assert rows[0]['features']['base']['bikes_lag30']==0
    # A later weather value must not fill the first hour's missing input.
    missing=join_historical_weather(data,weather.iloc[1:])
    assert learning_rows(historical_examples(missing))==[]
