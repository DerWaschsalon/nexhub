"""Parses: Dungeon-Namen und Schwierigkeiten sowie DPS-Vergleichswerte von Abyss Logs

Revision: 0019
Vorgänger: 0018
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dungeon_info",
        sa.Column("dungeon_id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("tier", sa.String(60), nullable=True),
        sa.Column("category", sa.String(60), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "parse_benchmarks",
        sa.Column("boss", sa.Integer, primary_key=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cells", sa.JSON, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("parse_benchmarks")
    op.drop_table("dungeon_info")
