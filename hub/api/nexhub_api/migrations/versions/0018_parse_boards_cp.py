"""Parses: Kampfkraft je Eintrag der Ranglisten, für den Vergleich im CP-Bereich

Revision: 0018
Vorgänger: 0017
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("parse_boards", sa.Column("cp", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("parse_boards", "cp")
