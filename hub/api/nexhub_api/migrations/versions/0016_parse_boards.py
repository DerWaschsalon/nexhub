"""Parses: zwischengespeicherte Ranglisten von Abyss Logs

Revision: 0016
Vorgänger: 0015
"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

BigID = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "parse_boards",
        sa.Column("id", BigID, primary_key=True),
        sa.Column("boss", sa.Integer, nullable=False),
        sa.Column("cls", sa.String(32), nullable=False),
        sa.Column("region", sa.String(8), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total", sa.Integer, nullable=False),
        sa.Column("dps", sa.JSON, nullable=False),
        sa.UniqueConstraint("boss", "cls", "region"),
    )


def downgrade() -> None:
    op.drop_table("parse_boards")
