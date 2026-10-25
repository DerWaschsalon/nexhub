"""Build-Check: letzter Vergleich eines Armory-Charakters mit den Top-Spielern

Revision: 0009
Vorgänger: 0008
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

BigID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "build_checks",
        sa.Column("id", BigID, primary_key=True),
        sa.Column("character_id", BigID, sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
                  unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.String(200)),
        sa.Column("result", sa.JSON),
        sa.Column("share_token", sa.String(32), unique=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("build_checks")
