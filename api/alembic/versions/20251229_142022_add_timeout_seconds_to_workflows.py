"""add_timeout_seconds_to_workflows

Revision ID: a1a14b958cf9
Revises: caad9196f150
Create Date: 2025-12-29 14:20:22.764893+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1a14b958cf9'
down_revision: Union[str, None] = 'caad9196f150'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'workflows',
        sa.Column('timeout_seconds', sa.Integer(), nullable=False, server_default='1800')
    )


def downgrade() -> None:
    op.drop_column('workflows', 'timeout_seconds')
