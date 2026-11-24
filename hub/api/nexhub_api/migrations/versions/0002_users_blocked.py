"""Konten sperren

Revision: 0002
Vorgänger: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as t:
        t.add_column(sa.Column("blocked_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    with op.batch_alter_table("users") as t:
        t.drop_column("blocked_at")
