"""add_is_local_execution_to_executions

Revision ID: aec8b0bd248d
Revises: a5cd74106a68
Create Date: 2025-12-12 23:09:12.585936+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aec8b0bd248d'
down_revision: Union[str, None] = 'a5cd74106a68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_local_execution column to executions table
    op.add_column(
        'executions',
        sa.Column('is_local_execution', sa.Boolean(), nullable=False, server_default='false')
    )
    # Create index for filtering local executions in history queries
    op.create_index('ix_executions_is_local_execution', 'executions', ['is_local_execution'])


def downgrade() -> None:
    op.drop_index('ix_executions_is_local_execution', table_name='executions')
    op.drop_column('executions', 'is_local_execution')
