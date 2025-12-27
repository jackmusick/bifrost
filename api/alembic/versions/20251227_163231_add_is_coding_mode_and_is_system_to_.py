"""add_is_coding_mode_and_is_system_to_agents

Revision ID: 0fc71a6c9de9
Revises: add_ai_metrics_columns
Create Date: 2025-12-27 16:32:31.993589+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0fc71a6c9de9'
down_revision: Union[str, None] = 'add_ai_metrics_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_coding_mode column
    op.add_column(
        'agents',
        sa.Column('is_coding_mode', sa.Boolean(), nullable=False, server_default='false')
    )
    # Add is_system column (for built-in agents that can't be deleted)
    op.add_column(
        'agents',
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default='false')
    )


def downgrade() -> None:
    op.drop_column('agents', 'is_system')
    op.drop_column('agents', 'is_coding_mode')
