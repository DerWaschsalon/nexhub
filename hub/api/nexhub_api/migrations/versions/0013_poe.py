"""Path of Exile: Preise, Preisverlauf und Beobachtungsliste

Revision: 0013
Vorgänger: 0012
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

BigID = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "poe_items",
        sa.Column("id", BigID, primary_key=True),
        sa.Column("game", sa.String(8), nullable=False),
        sa.Column("league", sa.String(64), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("category", sa.String(48), nullable=False),
        sa.Column("icon", sa.String(512)),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("listings", sa.Integer),
        sa.Column("trade_volume", sa.Float),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("game", "league", "key"),
    )
    op.create_table(
        "poe_prices",
        sa.Column("id", BigID, primary_key=True),
        sa.Column("game", sa.String(8), nullable=False),
        sa.Column("league", sa.String(64), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.UniqueConstraint("game", "league", "key", "day"),
    )
    op.create_table(
        "poe_watches",
        sa.Column("id", BigID, primary_key=True),
        sa.Column("user_id", BigID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("game", sa.String(8), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("threshold", sa.Float, nullable=False, server_default="20"),
        sa.Column("ref_price", sa.Float),
        sa.Column("ref_league", sa.String(64)),
        sa.Column("alerted_on", sa.Date),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "game", "key"),
    )


def downgrade() -> None:
    op.drop_table("poe_watches")
    op.drop_table("poe_prices")
    op.drop_table("poe_items")
