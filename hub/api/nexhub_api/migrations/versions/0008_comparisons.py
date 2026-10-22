"""Geteilte Vergleiche aus der Armory

Revision: 0008
Vorgänger: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

BigID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "comparisons",
        sa.Column("id", BigID, primary_key=True),
        sa.Column("token", sa.String(32), nullable=False, unique=True),
        sa.Column("user_id", BigID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("left_id", BigID, sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("right_server_id", sa.Integer, nullable=False),
        sa.Column("right_name", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_comparisons_user_id", "comparisons", ["user_id"])
    op.create_index("ix_comparisons_left_id", "comparisons", ["left_id"])


def downgrade() -> None:
    op.drop_table("comparisons")
