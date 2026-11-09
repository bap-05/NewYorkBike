from fastapi import APIRouter

from backend.app.routers.common import Context

router=APIRouter(tags=['Health'])


@router.get('/health/live')
def live():
    """Process liveness; does not connect to MySQL."""
    return {'status':'ok'}


@router.get('/health/ready')
def ready(ctx:Context):
    """MySQL connection and required schema are ready, not a data freshness claim."""
    return {'status':'ready','required_revision':'0006_prediction','database_access':'read_only'}
