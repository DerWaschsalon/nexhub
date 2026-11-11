"""Bewertung der Ausrüstung: Zählung der Top-Spieler je Klasse und Würfeltabellen je Gegenstand

Revision: 0011
Vorgänger: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "class_census",
        sa.Column("cls", sa.String(32), primary_key=True),
        sa.Column("group_label", sa.String(300), nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "item_rolls",
        sa.Column("name", sa.String(128), primary_key=True),
        sa.Column("data", sa.JSON),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("item_rolls")
    op.drop_table("class_census")
