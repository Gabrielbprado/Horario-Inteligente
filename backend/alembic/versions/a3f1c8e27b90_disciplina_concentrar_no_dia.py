"""disciplina.concentrar_no_dia

Revision ID: a3f1c8e27b90
Revises: d25eb52a1d41
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3f1c8e27b90"
down_revision: str | Sequence[str] | None = "d25eb52a1d41"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "disciplina",
        sa.Column("concentrar_no_dia", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("disciplina", "concentrar_no_dia")
