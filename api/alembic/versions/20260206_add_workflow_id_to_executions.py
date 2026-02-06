"""add_workflow_id_to_executions

Revision ID: b2d4e6f83c01
Revises: a1c3f5e72b90
Create Date: 2026-02-06 12:00:00.000000+00:00

Add workflow_id FK column to executions table to link executions
directly to workflows by UUID instead of relying solely on workflow_name.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b2d4e6f83c01'
down_revision: Union[str, None] = 'a1c3f5e72b90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'executions',
        sa.Column('workflow_id', sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        'fk_executions_workflow_id',
        'executions',
        'workflows',
        ['workflow_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_executions_workflow_id', 'executions', ['workflow_id'])


def downgrade() -> None:
    op.drop_index('ix_executions_workflow_id', table_name='executions')
    op.drop_constraint('fk_executions_workflow_id', 'executions', type_='foreignkey')
    op.drop_column('executions', 'workflow_id')
