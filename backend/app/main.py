"""FastAPI factory: no DB connection on import, no worker/scheduler side effects."""
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from backend.app.config import ApiOptions
from backend.app.routers import analytics, health, overview, stations
from shared.config import Settings
from shared.database import make_engine
from shared.presentation import APP_NAME
from shared.time import utcnow

logger=logging.getLogger('citibike.api')


def create_app(*,settings=None,options=None,engine=None,clock=utcnow):
    @asynccontextmanager
    async def lifespan(app):
        app.state.settings=settings if settings is not None else Settings.load(outbound=False)
        app.state.options=options if options is not None else ApiOptions.load()
        app.state.engine=engine if engine is not None else make_engine(app.state.settings)
        app.state.clock=clock
        app.state.validated_schema=None
        try:
            yield
        finally:
            if engine is None:
                app.state.engine.dispose()

    application=FastAPI(title=f'{APP_NAME} API',version='1.0.0',lifespan=lifespan,
        description='Read-only public data API. UTC timestamps include New York display offsets. Workers run independently.')
    # Config is loaded at lifespan, so middleware reads the validated allowlist per request.
    # A small ASGI wrapper below keeps .env/engine initialization out of module import.
    class DynamicCors:
        def __init__(self,app):
            self.app=app
            self.cors=None

        async def __call__(self,scope,receive,send):
            if scope['type']=='lifespan':
                await self.app(scope,receive,send)
                return
            if self.cors is None:
                self.cors=CORSMiddleware(self.app,allow_origins=list(application.state.options.cors_origins),
                    allow_credentials=False,allow_methods=['GET'],allow_headers=['Accept','Content-Type'])
            await self.cors(scope,receive,send)

    application.add_middleware(DynamicCors)

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request:Request,exc:SQLAlchemyError):
        logger.warning('Database request failed (%s)',type(exc).__name__)
        return JSONResponse(status_code=503,content={'detail':'Database temporarily unavailable. Try again later.'})

    @application.exception_handler(Exception)
    async def unexpected_error(request:Request,exc:Exception):
        logger.error('API request failed (%s)',type(exc).__name__)
        return JSONResponse(status_code=500,content={'detail':'An unexpected server error occurred.'})

    for router in (health.router,overview.router,stations.router,analytics.router):
        application.include_router(router)
    return application


app=create_app()
