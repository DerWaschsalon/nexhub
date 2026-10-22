"""Armory: eingetragene Charaktere und ihr Verlauf je Tag

Revision: 0007
Vorgänger: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

BigID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "characters",
        sa.Column("id", BigID, primary_key=True),
        sa.Column("user_id", BigID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        # wie run_characters (models.Snapshot)
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("cls", sa.String(32)),
        sa.Column("server_id", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("nc_character_id", sa.String(128)),
        sa.Column("combat_power", sa.BigInteger),
        sa.Column("item_level", sa.Integer),
        sa.Column("data", sa.JSON),
        sa.Column("error", sa.String(200)),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("server_id", "nc_character_id", name="uq_characters_server_nc"),
    )
    op.create_index("ix_characters_user_id", "characters", ["user_id"])
    op.create_index("ix_characters_status", "characters", ["status"])
    op.create_table(
        "character_days",
        sa.Column("id", BigID, primary_key=True),
        sa.Column("character_id", BigID, sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("combat_power", sa.BigInteger),
        sa.Column("item_level", sa.Integer),
        sa.UniqueConstraint("character_id", "day", name="uq_character_days_character_day"),
    )
    op.create_index("ix_character_days_character_id", "character_days", ["character_id"])


def downgrade() -> None:
    op.drop_table("character_days")
    op.drop_table("characters")
