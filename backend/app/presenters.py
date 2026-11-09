"""Serialize explicit public fields; preserve NULLs, UTC and New York offsets."""
import math
from zoneinfo import ZoneInfo

from shared.time import as_utc

ZONE=ZoneInfo('America/New_York')


def timestamp(value):
    return {'utc':as_utc(value),'local':as_utc(value).astimezone(ZONE)} if value is not None else None


def meta(ctx,source):
    return {'source':source,'timezone':'America/New_York','as_of':timestamp(ctx.now)}


def bike_view(ctx,bike):
    if bike is None:
        return None
    age=(ctx.now-bike.source_observed_at).total_seconds() if bike.source_observed_at else None
    sample_age=(ctx.now-bike.sampled_at).total_seconds()
    status='fresh'
    if bike.is_installed is False or bike.is_renting is False or bike.quality_status=='inactive':
        status='inactive'
    elif bike.available_bikes is None or bike.quality_status=='missing':
        status='missing'
    elif bike.quality_status=='invalid' or bike.available_bikes<0:
        status='invalid'
    elif bike.quality_status=='stale' or sample_age>ctx.options.bike_max_age_seconds or (age is not None and age>ctx.options.bike_max_age_seconds):
        status='stale'
    elif age is None or bike.is_installed is not True or bike.is_renting is not True:
        status='unknown'
    return {'id':bike.id,'sampled_at':timestamp(bike.sampled_at),'collected_at':timestamp(bike.collected_at),
        'source_observed_at':timestamp(bike.source_observed_at),'available_bikes':bike.available_bikes,
        'available_docks':bike.available_docks,'is_installed':bike.is_installed,'is_renting':bike.is_renting,
        'is_returning':bike.is_returning,'quality_status':bike.quality_status,'availability_status':status,
        'is_current':status=='fresh','age_seconds':age}


def finite(value):
    return value if value is None or math.isfinite(value) else None


def weather_view(ctx,weather,station):
    if weather is None:
        return None
    values={name:finite(getattr(weather,name)) for name in ('temperature','humidity','rain','wind_speed')}
    age=(ctx.now-weather.weather_time).total_seconds()
    status='fresh'
    required=('temperature_2m','relative_humidity_2m','rain','wind_speed_10m')
    if weather.source!='open-meteo' or weather.requested_latitude!=station.latitude or weather.requested_longitude!=station.longitude:
        status='invalid'
    elif (any(v is None for v in values.values()) or any(not (weather.units or {}).get(k) for k in required)):
        status='partial'
    elif not 0<=weather.humidity<=100 or weather.rain<0 or weather.wind_speed<0 or weather.interval_seconds<=0:
        status='invalid'
    elif age>ctx.settings.weather_max_age_seconds:
        status='stale'
    return {'id':weather.id,'source':weather.source,'weather_time':timestamp(weather.weather_time),
        'collected_at':timestamp(weather.collected_at),'interval_seconds':weather.interval_seconds,
        'units':weather.units or {},'requested_latitude':float(weather.requested_latitude),
        'requested_longitude':float(weather.requested_longitude),'status':status,'age_seconds':age,**values}


def station_view(ctx,station,bike=None,weather=None):
    observation=bike_view(ctx,bike)
    return {'source':station.source,'station_id':station.station_id,'name':station.name,
        'latitude':float(station.latitude),'longitude':float(station.longitude),'capacity':station.capacity,
        'is_monitored':station.is_monitored,'metadata_updated_at':timestamp(station.updated_at),
        'availability_status':observation['availability_status'] if observation else 'missing',
        'latest_observation':observation,'latest_weather':weather_view(ctx,weather,station)}


def prediction_view(ctx,prediction,model=None,latest_bike=None,input_bike=None):
    reason=None
    if prediction.status=='unavailable':
        reason=prediction.reason or 'worker_reported_unavailable'
    elif prediction.target_at is None or prediction.target_at<=ctx.now:
        reason='target_passed'
    elif (ctx.now-prediction.issued_at).total_seconds()>ctx.options.prediction_max_age_seconds:
        reason='prediction_stale'
    elif prediction.input_time is None or (ctx.now-prediction.input_time).total_seconds()>ctx.options.bike_max_age_seconds:
        reason='input_observation_stale'
    elif input_bike is None:
        reason='input_observation_unavailable'
    elif bike_view(ctx,input_bike)['availability_status']!='fresh':
        reason='input_observation_unusable'
    elif latest_bike is not None and bike_view(ctx,latest_bike)['availability_status']!='fresh':
        reason='latest_station_observation_unusable'
    model_view={'id':model.id,'name':model.name,'kind':model.kind,'trained_at':timestamp(model.trained_at)} if model else None
    evaluated=prediction.evaluated_at is not None and prediction.evaluated_at<=ctx.now
    return {'id':prediction.id,'status':prediction.status,'reason':prediction.reason,
        'input_time':timestamp(prediction.input_time),'input_cutoff_at':timestamp(prediction.input_cutoff_at),
        'input_source_observed_at':timestamp(input_bike.source_observed_at) if input_bike else None,
        'target_at':timestamp(prediction.target_at),'issued_at':timestamp(prediction.issued_at),
        'predicted_bikes':finite(prediction.predicted_bikes),'raw_predicted_bikes':finite(prediction.raw_predicted_bikes),
        'model':model_view,'is_current':reason is None,'display_reason':reason,
        'actual_bikes':prediction.actual_bikes if evaluated else None,'actual_time':timestamp(prediction.actual_time) if evaluated else None,
        'target_offset_seconds':prediction.target_offset_seconds if evaluated else None,'evaluated_at':timestamp(prediction.evaluated_at) if evaluated else None,
        'absolute_error':finite(prediction.absolute_error) if evaluated else None,'squared_error':finite(prediction.squared_error) if evaluated else None}


def analysis_view(row):
    return {**{name:getattr(row,name) for name in ('id','station_id','aggregation','metric_name','sample_count',
        'observed_sample_count','expected_sample_count','coverage','quality_status','dimensions','configuration_hash','calculation_version')},
        'metric_value':finite(row.metric_value),**{name:timestamp(getattr(row,name)) for name in (
            'window_start','window_end','input_cutoff','calculated_at')}}


def cluster_run_view(run):
    if run is None:
        return None
    parameters,summary=run.parameters or {},run.summary or {}
    return {'id':run.id,'run_date':run.run_date,'status':run.status,'algorithm':run.algorithm,
        'calculation_version':run.calculation_version,'configuration_hash':run.configuration_hash,
        'window_start':timestamp(run.window_start),'window_end':timestamp(run.window_end),
        'finished_at':timestamp(run.finished_at),'selected_k':parameters.get('selected_k'),
        'silhouette':finite(parameters.get('silhouette')),'feature_names':parameters.get('feature_names',[]),
        'eligible_stations':summary.get('eligible_stations'),'reason':parameters.get('reason')}
