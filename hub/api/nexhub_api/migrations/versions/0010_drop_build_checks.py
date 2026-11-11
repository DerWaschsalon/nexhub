"""Build-Check entfernt: Tabelle build_checks fällt weg

Revision: 0010
Vorgänger: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

BigID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.drop_table("build_checks")


def downgrade() -> None:
    # wie 0009, damit ein Zurückgehen dieselbe (leere) Tabelle wieder anlegt
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
