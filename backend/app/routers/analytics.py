from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query
from sqlalchemy import select

from backend.app import repositories as repo
from backend.app.presenters import analysis_view, cluster_run_view, meta
from backend.app.routers.common import ConfigHash, Context, Limit, Offset, Source, StationId, date_range
from backend.app.routers.stations import Start, End
from backend.app.schemas import AnalysisPage, ClusterPage, ClusterResponse
from shared.models import AnalysisResult, StationCluster

router=APIRouter(prefix='/api',tags=['Analysis and Clustering'])


@router.get('/analysis',response_model=AnalysisPage)
def analysis(ctx:Context,source:Source='citibike',station_id:StationId|None=None,
        aggregation:Literal['hour','day']='hour',metric_name:Annotated[str|None,Query(max_length=64)]=None,
        configuration_hash:ConfigHash=None,start:Start=None,end:End=None,limit:Limit=100,offset:Offset=0):
    """Gold đã công bố; mặc định một configuration_hash mới nhất, không trộn cấu hình."""
    start,end=date_range(ctx,start,end,default_days=7)
    query,digest=repo.analysis_query(ctx,source,configuration_hash=configuration_hash)
    query=query.where(AnalysisResult.aggregation==aggregation,AnalysisResult.window_start>=start,AnalysisResult.window_start<end)
    if station_id:
        repo.station_or_404(ctx,source,station_id)
        query=query.where(AnalysisResult.station_id==station_id)
    if metric_name:
        query=query.where(AnalysisResult.metric_name==metric_name)
    rows,pagination=repo.page(ctx,query.order_by(AnalysisResult.window_start.desc(),AnalysisResult.station_id,AnalysisResult.id),limit,offset)
    return {'meta':meta(ctx,source),'pagination':pagination,'configuration_hash':digest,'items':[analysis_view(r) for r in rows]}


@router.get('/clusters',response_model=ClusterResponse)
def clusters(ctx:Context,source:Source='citibike',configuration_hash:ConfigHash=None):
    latest,success=repo.cluster_attempts(ctx,source,configuration_hash)
    status='available' if success else latest.status if latest else 'missing'
    return {'meta':meta(ctx,source),'status':status,'latest_attempt':cluster_run_view(latest),'latest_success':cluster_run_view(success)}


@router.get('/clusters/{run_id}/stations',response_model=ClusterPage)
def cluster_stations(run_id:Annotated[int,Path(ge=1,le=2147483647)],ctx:Context,source:Source='citibike',limit:Limit=100,offset:Offset=0):
    run=repo.published_cluster(ctx,source,run_id)
    query=select(StationCluster).where(StationCluster.source==source,StationCluster.clustering_run_id==run.id)
    rows,pagination=repo.page(ctx,query.order_by(StationCluster.cluster_label,StationCluster.station_id),limit,offset)
    fields=('station_id','cluster_label','distance_to_centroid','feature_values','metadata_snapshot',
        'sample_count','expected_sample_count','coverage')
    return {'meta':meta(ctx,source),'pagination':pagination,'run':cluster_run_view(run),
        'items':[{name:getattr(row,name) for name in fields} for row in rows]}
