"""Request-scoped read-only sessions; no scheduler, migration or worker startup."""
from dataclasses import dataclass
from datetime import datetime

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import HTTPException, Request
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from backend.app.config import ApiOptions
from shared.config import ROOT, Settings
from shared.models import Base
from shared.time import as_utc


@dataclass
class ReadContext:
    session: Session
    settings: Settings
    options: ApiOptions
    now: datetime


def require_schema(connection,app):
    heads=MigrationContext.configure(connection).get_current_heads()
    if heads==getattr(app.state,'validated_schema',None):
        return
    try:
        if len(heads)!=1:
            raise ValueError('Expected a single migration head')
        scripts=ScriptDirectory.from_config(Config(str(ROOT/'alembic.ini')))
        ancestors={r.revision for r in scripts.walk_revisions(base='base',head=heads[0])}
        if '0006_prediction' not in ancestors:
            raise ValueError('Required migration missing')
        inspector=inspect(connection)
        for table in Base.metadata.sorted_tables:
            if not set(table.columns.keys()) <= {c['name'] for c in inspector.get_columns(table.name)}:
                raise ValueError('Required columns missing')
    except Exception:
        raise HTTPException(503,detail='Database schema is not ready. Apply the documented migrations.') from None
    app.state.validated_schema=heads


def get_context(request:Request):
    app=request.app
    now=as_utc(app.state.clock())
    with app.state.engine.connect() as connection:
        dialect=connection.dialect.name
        if dialect=='mysql':
            connection.exec_driver_sql('SET SESSION TRANSACTION READ ONLY')
            connection.commit()
        elif dialect=='sqlite':
            connection.exec_driver_sql('PRAGMA query_only=ON')
        try:
            require_schema(connection,app)
            with Session(bind=connection,autoflush=False) as session:
                try:
                    yield ReadContext(session,app.state.settings,app.state.options,now)
                finally:
                    session.rollback()
        finally:
            connection.rollback()
            if dialect=='sqlite':
                connection.exec_driver_sql('PRAGMA query_only=OFF')
