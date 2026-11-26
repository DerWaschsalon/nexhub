"""Parses: Legionen, die im Gildenvergleich zählen

Revision: 0017
Vorgänger: 0016
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guild_legions",
        sa.Column("name", sa.String(64), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("guild_legions")
