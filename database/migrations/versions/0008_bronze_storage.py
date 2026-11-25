"""Store Bronze captures in MySQL with an index for retention cleanup."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGBLOB

revision = "0008_bronze_storage"
down_revision = "0007_vietnamese_names"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "du_lieu_tho_bronze",
        sa.Column("archive_path", sa.String(255), primary_key=True),
        sa.Column("stored_at", sa.DateTime(), nullable=False),
        sa.Column("manifest", sa.JSON()),
        sa.Column("compressed_body", LONGBLOB()),
    )
    op.create_index("ix_du_lieu_tho_bronze_stored_at", "du_lieu_tho_bronze", ["stored_at"])


def downgrade():
    op.drop_table("du_lieu_tho_bronze")
