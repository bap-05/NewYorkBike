"""Read-only minimum-revision checks: independent services evolve additively."""
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from shared.config import ROOT
from shared.database import make_engine


def check_schema(settings, *, required_revision, models):
    engine = make_engine(settings)
    try:
        with engine.connect() as connection:
            scripts = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
            actual = MigrationContext.configure(connection).get_current_heads()
            if len(actual) != 1:
                raise ValueError("Expected one recorded migration head")
            head=actual[0]
            # Explicit bridge for older deployed workers using the updatable English views.
            if head=='0007_vietnamese_names' and not (ROOT/'database/migrations/versions/0007_vietnamese_names.py').is_file():
                head='0006_prediction'
            ancestors = {revision.revision for revision in scripts.walk_revisions(base="base", head=head)}
            if required_revision not in ancestors:
                raise ValueError("Database is below the minimum revision required by this service")
            inspector = inspect(connection)
            for model in models:
                available = {column["name"] for column in inspector.get_columns(model.__tablename__)}
                if not {column.name for column in model.__table__.columns} <= available:
                    raise ValueError("Required service columns are missing")
    finally:
        engine.dispose()
