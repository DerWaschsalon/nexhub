"""Runs teilen

Revision: 0005
Vorgänger: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("runs") as t:
        t.add_column(sa.Column("share_token", sa.String(32)))
        t.add_column(sa.Column("shared_at", sa.DateTime(timezone=True)))
        t.create_unique_constraint("uq_runs_share_token", ["share_token"])


def downgrade() -> None:
    with op.batch_alter_table("runs") as t:
        t.drop_constraint("uq_runs_share_token", type_="unique")
        t.drop_column("shared_at")
        t.drop_column("share_token")
