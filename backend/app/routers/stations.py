from typing import Annotated

from fastapi import APIRouter, Path, Query
from pydantic import AwareDatetime

from backend.app import repositories as repo
from backend.app.presenters import bike_view, meta, prediction_view, station_view, weather_view
from backend.app.routers.common import Context, Limit, Offset, Source, date_range
from backend.app.schemas import (HistoryPage, LatestPredictionResponse, PredictionPage, StationPage, StationResponse)
from shared.models import Prediction

router=APIRouter(prefix='/api/stations',tags=['Stations'])
StationPath=Annotated[str,Path(min_length=1,max_length=128)]
Start=Annotated[AwareDatetime|None,Query(alias='from')]
End=Annotated[AwareDatetime|None,Query(alias='to')]


@router.get('',response_model=StationPage)
def list_stations(ctx:Context,source:Source='citibike',q:Annotated[str|None,Query(max_length=100)]=None,
        monitored_only:bool=True,limit:Limit=100,offset:Offset=0):
    """Danh sách trạm và quan sát mới nhất, gồm nhãn dữ liệu cũ/inactive."""
    stations,pagination=repo.page(ctx,repo.station_query(source,q=q,monitored_only=monitored_only),limit,offset)
    bikes=repo.latest_bikes(ctx,source,[s.station_id for s in stations])
    weather=repo.linked_weather(ctx,source,list(bikes.values()))
    return {'meta':meta(ctx,source),'pagination':pagination,'items':[
        station_view(ctx,s,bikes.get(s.station_id),weather.get(bikes[s.station_id].id) if s.station_id in bikes else None)
        for s in stations]}


@router.get('/{station_id}',response_model=StationResponse)
def station_detail(station_id:StationPath,ctx:Context,source:Source='citibike'):
    station=repo.station_or_404(ctx,source,station_id)
    bike=repo.latest_bikes(ctx,source,[station_id]).get(station_id)
    weather=repo.linked_weather(ctx,source,[bike]).get(bike.id) if bike else None
    forecast=ctx.session.scalar(repo.forecast_query(ctx,source,station_id).order_by(Prediction.issued_at.desc(),Prediction.id.desc()).limit(1))
    model=repo.models_for(ctx,source,[forecast]).get(forecast.model_version_id) if forecast else None
    item=station_view(ctx,station,bike,weather)
    input_bike=repo.input_bikes_for(ctx,source,[forecast]).get(forecast.input_observation_id) if forecast else None
    item['latest_prediction']=prediction_view(ctx,forecast,model,bike,input_bike) if forecast else None
    return {'meta':meta(ctx,source),'item':item}


@router.get('/{station_id}/history',response_model=HistoryPage)
def station_history(station_id:StationPath,ctx:Context,source:Source='citibike',start:Start=None,end:End=None,
        limit:Limit=200,offset:Offset=0):
    station=repo.station_or_404(ctx,source,station_id)
    start,end=date_range(ctx,start,end)
    rows,pagination=repo.page(ctx,repo.history_query(ctx,source,station_id,start,end),limit,offset)
    weather=repo.linked_weather(ctx,source,rows)
    return {'meta':meta(ctx,source),'pagination':pagination,'items':[
        {'observation':bike_view(ctx,b),'weather':weather_view(ctx,weather.get(b.id),station)} for b in rows]}


@router.get('/{station_id}/predictions/latest',response_model=LatestPredictionResponse)
def latest_prediction(station_id:StationPath,ctx:Context,source:Source='citibike'):
    repo.station_or_404(ctx,source,station_id)
    forecast=ctx.session.scalar(repo.forecast_query(ctx,source,station_id).order_by(Prediction.issued_at.desc(),Prediction.id.desc()).limit(1))
    if forecast is None:
        return {'meta':meta(ctx,source),'item':None,'status':'missing'}
    bike=repo.latest_bikes(ctx,source,[station_id]).get(station_id)
    model=repo.models_for(ctx,source,[forecast]).get(forecast.model_version_id)
    input_bike=repo.input_bikes_for(ctx,source,[forecast]).get(forecast.input_observation_id)
    item=prediction_view(ctx,forecast,model,bike,input_bike)
    return {'meta':meta(ctx,source),'item':item,'status':'available' if item['is_current'] else 'unavailable'}


@router.get('/{station_id}/predictions',response_model=PredictionPage)
def station_predictions(station_id:StationPath,ctx:Context,source:Source='citibike',start:Start=None,end:End=None,
        limit:Limit=100,offset:Offset=0):
    repo.station_or_404(ctx,source,station_id)
    start,end=date_range(ctx,start,end)
    rows,pagination=repo.page(ctx,repo.forecast_query(ctx,source,station_id).where(
        Prediction.issued_at>=start,Prediction.issued_at<end).order_by(Prediction.issued_at.desc(),Prediction.id.desc()),limit,offset)
    models=repo.models_for(ctx,source,rows)
    input_bikes=repo.input_bikes_for(ctx,source,rows)
    bike=repo.latest_bikes(ctx,source,[station_id]).get(station_id)
    return {'meta':meta(ctx,source),'pagination':pagination,'items':[
        prediction_view(ctx,p,models.get(p.model_version_id),bike,input_bikes.get(p.input_observation_id)) for p in rows]}
