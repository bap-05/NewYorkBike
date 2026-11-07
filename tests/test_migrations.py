import importlib.util
from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from shared.models import Base


def migration():
    path = Path(__file__).resolve().parents[1] / "database/migrations/versions/0001_ingestion.py"
    spec = importlib.util.spec_from_file_location("initial_schema", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_matches_models_and_downgrade():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        module = migration()
        with Operations.context(context):
            module.upgrade()
            assert set(inspect(connection).get_table_names()) == {
                "stations", "collection_runs", "bike_observations", "weather_observations", "observation_weather_links"}
            # 0001 stays frozen as legacy; source-aware schema is introduced in 0002.
            module.downgrade()
            assert inspect(connection).get_table_names() == []


def test_mysql_migration_compiles_without_credentials():
    output = StringIO()
    context = MigrationContext.configure(dialect_name="mysql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        migration().upgrade()
    sql = output.getvalue()
    assert sql.count("CREATE TABLE") == 5
    assert "DATETIME(6)" in sql and "utf8mb4_bin" in sql and "InnoDB" in sql
    assert "uq_bike_station_sample" in sql and "uq_weather_location_time_source" in sql
    assert "ON DELETE RESTRICT" in sql


def test_source_migration_has_no_table_or_column_removal():
    import ast
    path = Path(__file__).resolve().parents[1] / "database/migrations/versions/0002_citibike.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    destructive = {"drop_table", "drop_column", "rename_table"}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr in destructive for node in ast.walk(tree))


def test_bronze_migration_keeps_legacy_rows():
    from sqlalchemy import text
    path = Path(__file__).resolve().parents[1] / "database/migrations/versions/0003_bronze.py"
    spec = importlib.util.spec_from_file_location("bronze_schema", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE collection_runs (id INTEGER PRIMARY KEY, source VARCHAR(64))"))
        connection.execute(text("INSERT INTO collection_runs (id, source) VALUES (1, 'legacy-test-only')"))
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
        row = connection.execute(text("SELECT id, source, bronze_manifest_path FROM collection_runs")).one()
        assert tuple(row) == (1, "legacy-test-only", None)


def analysis_migration():
    path = Path(__file__).resolve().parents[1] / "database/migrations/versions/0004_analysis.py"
    spec = importlib.util.spec_from_file_location("analysis_schema", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_analysis_migration_adds_gold_without_changing_silver():
    from sqlalchemy import text
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration().upgrade()
        connection.execute(text("INSERT INTO stations (station_id,name,latitude,longitude,is_monitored,updated_at) VALUES ('test-only','Unit test',40,-74,1,'2026-01-01')"))
        before = {t: [c['name'] for c in inspect(connection).get_columns(t)] for t in inspect(connection).get_table_names()}
        with Operations.context(context):
            analysis_migration().upgrade()
        inspector = inspect(connection)
        assert set(inspector.get_table_names()) == set(Base.metadata.tables)
        for table, columns in before.items():
            assert [c['name'] for c in inspector.get_columns(table)] == columns
        assert connection.scalar(text("SELECT COUNT(*) FROM stations")) == 1


def test_analysis_schema_compiles_for_mysql_with_primary_keys_and_source_fks():
    output = StringIO()
    context = MigrationContext.configure(dialect_name="mysql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        analysis_migration().upgrade()
    sql = output.getvalue()
    assert sql.count("CREATE TABLE") == 2
    assert sql.count("PRIMARY KEY") == 2
    assert "FOREIGN KEY(source, station_id)" in sql
    assert "FOREIGN KEY(source, service_run_id)" in sql
    assert "DROP" not in sql and "ALTER" not in sql
