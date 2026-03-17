"""drop llm_temperature column from agents

Revision ID: 20260316_drop_llm_temp
Revises: 20260306_add_exec_context
Create Date: 2026-03-16
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "20260316_drop_llm_temp"
down_revision: Union[str, None] = "20260306_add_exec_context"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('agents', 'llm_temperature')


def downgrade() -> None:
    op.add_column('agents', sa.Column('llm_temperature', sa.Float(), nullable=True))
