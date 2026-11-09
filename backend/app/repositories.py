"""Bounded SQL reads, preserving source identities and worker publication rules."""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from shared.models import (AnalysisResult, BikeObservation, ClusteringRun, CollectionRun,
    ModelVersion, ObservationWeatherLink, Prediction, ServiceRun, Station, StationCluster, WeatherObservation)
from shared.repositories.gold import analysis_results, latest_clustering_run, predictions
from shared.repositories.silver import bike_observations


def station_query(source,*,q=None,monitored_only=True):
    query=select(Station).where(Station.source==source)
    if monitored_only:
        query=query.where(Station.is_monitored.is_(True))
    if q:
        query=query.where(func.lower(Station.name).contains(q.lower(),autoescape=True))
    return query.order_by(Station.station_id)


def station_or_404(ctx,source,station_id):
    station=ctx.session.get(Station,(source,station_id))
    if station is None:
        raise HTTPException(404,detail='Station not found in the selected source')
    return station


def page(ctx,query,limit,offset):
    total=ctx.session.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    return list(ctx.session.scalars(query.limit(limit).offset(offset))),{
        'total':total,'limit':limit,'offset':offset,'has_more':offset+limit<total}


def latest_bikes(ctx,source,ids):
    if not ids:
        return {}
    ranked=bike_observations(source=source,available_at=ctx.now,include_unusable=True).with_only_columns(
        BikeObservation.id.label('id'),func.row_number().over(partition_by=BikeObservation.station_id,
            order_by=(BikeObservation.sampled_at.desc(),BikeObservation.collected_at.desc(),BikeObservation.id.desc())).label('rn')
        ).where(BikeObservation.station_id.in_(ids),BikeObservation.sampled_at<=ctx.now).subquery()
    return {b.station_id:b for b in ctx.session.scalars(select(BikeObservation).join(ranked,
        ranked.c.id==BikeObservation.id).where(ranked.c.rn==1))}


def linked_weather(ctx,source,bikes):
    ids=[b.id for b in bikes]
    if not ids:
        return {}
    run=aliased(CollectionRun)
    rows=ctx.session.execute(select(ObservationWeatherLink.bike_observation_id,WeatherObservation)
        .join(WeatherObservation,WeatherObservation.id==ObservationWeatherLink.weather_observation_id)
        .outerjoin(run,run.id==WeatherObservation.collection_run_id)
        .where(ObservationWeatherLink.bike_observation_id.in_(ids),WeatherObservation.collected_at<=ctx.now,
            WeatherObservation.weather_time<=ctx.now,
            (WeatherObservation.collection_run_id.is_(None))|(
                (run.source==source)&run.status.in_(('success','partial'))&run.finished_at.is_not(None)&(run.finished_at<=ctx.now))))
    return dict(rows.all())


def history_query(ctx,source,station_id,start,end):
    return bike_observations(source=source,available_at=ctx.now,include_unusable=True).where(
        BikeObservation.station_id==station_id,BikeObservation.sampled_at>=start,
        BikeObservation.sampled_at<end).order_by(BikeObservation.sampled_at,BikeObservation.id)


def forecast_query(ctx,source,station_id):
    return predictions(source=source,available_at=ctx.now).where(Prediction.station_id==station_id)


def models_for(ctx,source,forecasts):
    ids={p.model_version_id for p in forecasts if p.model_version_id is not None}
    return {m.id:m for m in ctx.session.scalars(select(ModelVersion).where(
        ModelVersion.source==source,ModelVersion.id.in_(ids)))} if ids else {}


def input_bikes_for(ctx,source,forecasts):
    ids={p.input_observation_id for p in forecasts if p.input_observation_id is not None}
    return {b.id:b for b in ctx.session.scalars(bike_observations(source=source,
        available_at=ctx.now,include_unusable=True).where(BikeObservation.id.in_(ids),
        BikeObservation.sampled_at<=ctx.now))} if ids else {}


def analysis_query(ctx,source,*,configuration_hash=None):
    selected=select(ServiceRun.configuration_hash,ServiceRun.calculation_version).where(
        ServiceRun.source==source,ServiceRun.service_name=='analysis',ServiceRun.status=='success',
        ServiceRun.finished_at.is_not(None),ServiceRun.finished_at<=ctx.now)
    if configuration_hash is not None:
        selected=selected.where(ServiceRun.configuration_hash==configuration_hash)
    version=ctx.session.execute(selected.order_by(ServiceRun.finished_at.desc(),ServiceRun.id.desc()).limit(1)).first()
    configuration_hash=version.configuration_hash if version else configuration_hash
    query=analysis_results(source=source,configuration_hash=configuration_hash).where(
        AnalysisResult.input_cutoff<=ctx.now,ServiceRun.finished_at<=ctx.now)
    if version is None:
        query=query.where(False)
    else:
        query=query.where(AnalysisResult.calculation_version==version.calculation_version)
    return query,configuration_hash


def cluster_attempts(ctx,source,configuration_hash=None):
    query=select(ClusteringRun).join(ServiceRun,
        (ServiceRun.source==ClusteringRun.source)&(ServiceRun.id==ClusteringRun.service_run_id)).where(
        ClusteringRun.source==source,ClusteringRun.started_at<=ctx.now,ServiceRun.service_name=='clustering')
    if configuration_hash:
        query=query.where(ClusteringRun.configuration_hash==configuration_hash)
    latest=ctx.session.scalar(query.order_by(ClusteringRun.run_date.desc(),ClusteringRun.started_at.desc(),ClusteringRun.id.desc()).limit(1))
    success=ctx.session.scalar(latest_clustering_run(source=source,configuration_hash=configuration_hash,available_at=ctx.now))
    return latest,success


def published_cluster(ctx,source,run_id):
    run=ctx.session.scalar(select(ClusteringRun).join(ServiceRun,
        (ServiceRun.source==ClusteringRun.source)&(ServiceRun.id==ClusteringRun.service_run_id)).where(
        ClusteringRun.source==source,ClusteringRun.id==run_id,ServiceRun.service_name=='clustering'))
    if run is None:
        raise HTTPException(404,detail='Clustering run not found in the selected source')
    control=ctx.session.get(ServiceRun,run.service_run_id)
    if (run.status!='success' or control.status!='success' or run.finished_at is None
            or control.finished_at is None or max(run.finished_at,control.finished_at)>ctx.now):
        raise HTTPException(409,detail={'code':'clustering_not_published','status':run.status})
    return run


def service_states(ctx,source):
    result=[]
    for name in ('analysis','clustering','prediction'):
        query=select(ServiceRun).where(ServiceRun.source==source,ServiceRun.service_name==name,ServiceRun.started_at<=ctx.now)
        attempt=ctx.session.scalar(query.order_by(ServiceRun.started_at.desc(),ServiceRun.id.desc()).limit(1))
        completed=ctx.session.scalar(query.where(ServiceRun.status.in_(('success','skipped')),
            ServiceRun.finished_at.is_not(None),ServiceRun.finished_at<=ctx.now)
            .order_by(ServiceRun.finished_at.desc(),ServiceRun.id.desc()).limit(1))
        result.append((name,attempt,completed))
    return result
