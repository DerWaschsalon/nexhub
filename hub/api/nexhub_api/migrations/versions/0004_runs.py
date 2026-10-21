"""Hochgeladene Runs

Revision: 0004
Vorgänger: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

BigID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", BigID, primary_key=True),
        sa.Column("user_id", BigID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", BigID, sa.ForeignKey("devices.id", ondelete="SET NULL")),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("dungeon_id", sa.Integer(), nullable=False),
        sa.Column("dungeon", sa.String(120), nullable=False),
        sa.Column("difficulty", sa.String(40)),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),
        sa.Column("end_ms", sa.BigInteger(), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("bosses_total", sa.Integer(), nullable=False),
        sa.Column("bosses_killed", sa.Integer(), nullable=False),
        sa.Column("fights", sa.Integer(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("character", sa.String(64)),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "sha256"),
    )
    op.create_index("ix_runs_user_id", "runs", ["user_id"])
    op.create_index("ix_runs_start_ms", "runs", ["start_ms"])


def downgrade() -> None:
    op.drop_table("runs")
