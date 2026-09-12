"""invalidate sessions stored before token hashing

Revision ID: 7f0f5a1c2d33
Revises: c4f6232596bf
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7f0f5a1c2d33"
down_revision: str | Sequence[str] | None = "c4f6232596bf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM sessions")


def downgrade() -> None:
    pass
