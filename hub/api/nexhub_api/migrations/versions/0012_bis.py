"""BiS-Listen: Warteschlange und rollierender Bestand der Top-Spieler je Klasse

Revision: 0012
Vorgänger: 0011
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

BigID = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "bis_queue",
        sa.Column("id", BigID, primary_key=True),
        sa.Column("cls", sa.String(32), nullable=False),
        sa.Column("player_name", sa.String(64), nullable=False),
        sa.Column("raid", sa.String(128), nullable=False),
        sa.Column("tier", sa.String(16), nullable=False),
        sa.Column("rank", sa.Integer, nullable=False, index=True),
        sa.Column("combat_power", sa.BigInteger),
        sa.Column("tries", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_table(
        "bis_samples",
        sa.Column("id", BigID, primary_key=True),
        sa.Column("cls", sa.String(32), nullable=False, index=True),
        sa.Column("character_key", sa.String(64), nullable=False, unique=True),
        sa.Column("raid", sa.String(128), nullable=False),
        sa.Column("tier", sa.String(16), nullable=False),
        sa.Column("combat_power", sa.BigInteger),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("bis_samples")
    op.drop_table("bis_queue")
