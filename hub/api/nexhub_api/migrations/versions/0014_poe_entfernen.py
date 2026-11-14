"""Path of Exile entfernt: Preise, Preisverlauf und Beobachtungsliste aus 0013 fallen weg

Revision: 0014
Vorgänger: 0013
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("poe_watches")
    op.drop_table("poe_prices")
    op.drop_table("poe_items")


def downgrade() -> None:
    # Die Daten sind nach upgrade() weg, leere Tabellen brächten nichts zurück. Zurück nur über eine Sicherung.
    raise NotImplementedError("0014 lässt sich nicht zurücknehmen, Daten nur aus einer Sicherung")
