"""Charakterprofile: Momentaufnahmen der Mitspieler je Run

Revision: 0006
Vorgänger: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

BigID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "run_characters",
        sa.Column("id", BigID, primary_key=True),
        sa.Column("run_id", BigID, sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
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
        sa.UniqueConstraint("run_id", "name", name="uq_run_characters_run_name"),
    )
    op.create_index("ix_run_characters_run_id", "run_characters", ["run_id"])
    op.create_index("ix_run_characters_status", "run_characters", ["status"])


def downgrade() -> None:
    op.drop_table("run_characters")
