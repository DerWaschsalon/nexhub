"""Geräte und Kopplung

Revision: 0003
Vorgänger: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

BigID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", BigID, primary_key=True),
        sa.Column("user_id", BigID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.String(40)),
    )
    op.create_index("ix_devices_user_id", "devices", ["user_id"])
    op.create_table(
        "device_pairings",
        sa.Column("device_code_hash", sa.String(64), primary_key=True),
        sa.Column("user_code", sa.String(8), nullable=False, unique=True),
        sa.Column("client_name", sa.String(64), nullable=False),
        sa.Column("client_version", sa.String(40)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by", BigID, sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("device_name", sa.String(64)),
    )


def downgrade() -> None:
    op.drop_table("device_pairings")
    op.drop_table("devices")
