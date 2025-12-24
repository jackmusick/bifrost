"""Add workflow economics columns

Revision ID: add_workflow_economics
Revises: 028071a17e8c
Create Date: 2025-12-23

Adds economics tracking columns to workflows table:
- time_saved: Minutes saved per execution (Integer)
- value: Flexible value unit (Numeric(10,2))

These columns allow workflows to define their economic impact,
which is then aggregated in execution metrics for reporting.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_workflow_economics'
down_revision: Union[str, None] = '028071a17e8c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add economics columns to workflows table
    op.add_column(
        'workflows',
        sa.Column('time_saved', sa.Integer(), server_default='0', nullable=False)
    )
    op.add_column(
        'workflows',
        sa.Column('value', sa.Numeric(10, 2), server_default='0', nullable=False)
    )


def downgrade() -> None:
    op.drop_column('workflows', 'value')
    op.drop_column('workflows', 'time_saved')
