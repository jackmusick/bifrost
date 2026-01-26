"""add_llm_override_to_agents

Revision ID: 490802e951dc
Revises: 8d1he52g6f80
Create Date: 2026-01-26 20:44:16.195178+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '490802e951dc'
down_revision: Union[str, None] = '8d1he52g6f80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agents', sa.Column('llm_model', sa.String(100), nullable=True))
    op.add_column('agents', sa.Column('llm_max_tokens', sa.Integer(), nullable=True))
    op.add_column('agents', sa.Column('llm_temperature', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('agents', 'llm_temperature')
    op.drop_column('agents', 'llm_max_tokens')
    op.drop_column('agents', 'llm_model')
