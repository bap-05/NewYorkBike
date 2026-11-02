from alembic import context

from shared.config import Settings
from shared.database import make_engine
from shared.models import Base


def run():
    settings = Settings.load()
    if context.is_offline_mode():
        context.configure(url=settings.database_url(), target_metadata=Base.metadata,
                          literal_binds=True, dialect_opts={"paramstyle": "named"}, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = make_engine(settings)
        try:
            with engine.connect() as connection:
                context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
                with context.begin_transaction():
                    context.run_migrations()
        finally:
            engine.dispose()


run()
