from collections import Counter

from fastapi import APIRouter

from backend.app import repositories as repo
from backend.app.presenters import bike_view, meta, timestamp
from backend.app.routers.common import Context, Source
from backend.app.schemas import Overview
from shared.presentation import DEFAULT_MAP_CENTER

router=APIRouter(prefix='/api',tags=['Overview'])


@router.get('/overview',response_model=Overview)
def overview(ctx:Context,source:Source='citibike'):
    stations=list(ctx.session.scalars(repo.station_query(source)))
    bikes=repo.latest_bikes(ctx,source,[s.station_id for s in stations])
    views=[bike_view(ctx,bikes.get(s.station_id)) for s in stations]
    fresh=[v for v in views if v is not None and v['is_current']]
    states=Counter(v['availability_status'] if v else 'missing' for v in views)
    return {'meta':meta(ctx,source),'station_count':len(stations),'observation_status_counts':dict(states),
        'fresh_available_bikes':sum(v['available_bikes'] for v in fresh) if fresh else None,
        'fresh_empty_station_count':sum(v['available_bikes']==0 for v in fresh),
        'fresh_low_bike_station_count':sum(0<v['available_bikes']<=3 for v in fresh),
        'services':[{'service_name':name,'last_attempt_id':attempt.id if attempt else None,
            'last_attempt_status':attempt.status if attempt else None,
            'last_attempt_started_at':timestamp(attempt.started_at) if attempt else None,
            'last_completed_at':timestamp(completed.finished_at) if completed else None}
            for name,attempt,completed in repo.service_states(ctx,source)],
        'map_center':DEFAULT_MAP_CENTER if source=='citibike' else {'latitude':37.5665,'longitude':126.9780}}
