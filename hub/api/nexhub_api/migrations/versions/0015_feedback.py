"""Feedback-Board: Wünsche der Mitglieder mit Stimmen und Status

Revision: 0015
Vorgänger: 0014
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

BigID = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", BigID, primary_key=True),
        sa.Column("user_id", BigID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("body", sa.String(2000), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="neu"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "feedback_votes",
        sa.Column("feedback_id", BigID, sa.ForeignKey("feedback.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", BigID, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("feedback_votes")
    op.drop_table("feedback")
