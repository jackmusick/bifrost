"""add_tool_call_message_fields

Revision ID: 23757e5d7dde
Revises: 490802e951dc
Create Date: 2026-01-29 20:24:46.675711+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '23757e5d7dde'
down_revision: Union[str, None] = '490802e951dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add tool_call to message_role enum
    op.execute("ALTER TYPE message_role ADD VALUE IF NOT EXISTS 'tool_call'")

    # Add new columns to messages table
    op.add_column('messages', sa.Column('tool_state', sa.String(20), nullable=True))
    op.add_column('messages', sa.Column('tool_result', postgresql.JSONB(), nullable=True))
    op.add_column('messages', sa.Column('tool_input', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('messages', 'tool_input')
    op.drop_column('messages', 'tool_result')
    op.drop_column('messages', 'tool_state')
    # Note: Cannot remove enum value in PostgreSQL
