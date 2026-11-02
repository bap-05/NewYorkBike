"""Add the latest Bronze manifest reference; existing Silver rows remain unchanged."""
from alembic import op
import sqlalchemy as sa

revision = "0003_bronze"
down_revision = "0002_citibike"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("collection_runs", sa.Column("bronze_manifest_path", sa.String(1024), nullable=True))


def downgrade():
    raise RuntimeError("Forward-only: keep Bronze provenance and existing history")
