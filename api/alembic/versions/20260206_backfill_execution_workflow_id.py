"""backfill_execution_workflow_id

Revision ID: c3e5f7a94d12
Revises: b2d4e6f83c01
Create Date: 2026-02-06 13:00:00.000000+00:00

Backfill workflow_id on existing executions by joining workflow_name
to the workflows table. This is a data-only migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3e5f7a94d12'
down_revision: Union[str, None] = 'b2d4e6f83c01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE executions e
        SET workflow_id = w.id
        FROM workflows w
        WHERE e.workflow_name = w.name
          AND e.workflow_id IS NULL
    """))


def downgrade() -> None:
    # Backfill is idempotent and non-destructive; nothing to undo
    pass
