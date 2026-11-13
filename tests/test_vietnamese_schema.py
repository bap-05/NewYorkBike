"""Name migration preserves data/FKs; both physical-name and legacy-view reads are checked."""
import importlib.util
import json
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

ROOT=Path(__file__).resolve().parents[1]


def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'database/migrations/versions'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_complete_name_migration_and_rollback_preserves_legacy_rows_and_foreign_keys():
    engine=create_engine('sqlite://')
    with engine.begin() as conn:
        # Use the frozen legacy schema; 0002 intentionally targets MySQL only.
        for statement in (ROOT/'tests/fixtures/schema_0006.sql').read_text(encoding='utf-8').split(';'):
            if statement.strip():conn.exec_driver_sql(statement)
        conn.execute(text("INSERT INTO stations (source,station_id,name,latitude,longitude,is_monitored,updated_at) VALUES ('citibike','TEST-VN','Preserved',40,-74,1,'2026-01-01')"))
        migration=load('0007_vietnamese_names')
        with Operations.context(MigrationContext.configure(conn)):
            # Operations.context does not initialize Alembic's EnvironmentContext proxy.
            original=migration.context.is_offline_mode
            migration.context.is_offline_mode=lambda:False
            try:
                migration.upgrade()
                migration.upgrade()  # Resume after a completed DDL phase is harmless.
                assert set(inspect(conn).get_table_names())=={p['name'] for p in migration.PLAN.values()}
                assert conn.scalar(text('SELECT ten FROM tram_xe'))=='Preserved'
                assert conn.scalar(text('SELECT name FROM stations'))=='Preserved'
                for old,plan in migration.PLAN.items():
                    assert {c['name'] for c in inspect(conn).get_columns(plan['name'])}==set(plan['columns'].values())
                    assert {c['name'] for c in inspect(conn).get_columns(old)}==set(plan['columns'])
                migration.downgrade()
                assert set(inspect(conn).get_table_names())==set(migration.PLAN)
                assert conn.scalar(text('SELECT name FROM stations'))=='Preserved'
                assert not inspect(conn).get_view_names()
            finally:
                migration.context.is_offline_mode=original
    engine.dispose()
