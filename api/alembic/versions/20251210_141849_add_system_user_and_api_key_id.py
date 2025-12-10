"""add_system_user_and_api_key_id

Revision ID: 311d0802e654
Revises: 99760511c232
Create Date: 2025-12-10 14:18:49.339807+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '311d0802e654'
down_revision: Union[str, None] = '99760511c232'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# System user UUID - well-known constant for API key executions
SYSTEM_USER_ID = '00000000-0000-0000-0000-000000000001'


def upgrade() -> None:
    # Add SYSTEM to user_type enum
    # Note: New enum values require a commit before they can be used
    op.execute("ALTER TYPE user_type ADD VALUE IF NOT EXISTS 'SYSTEM'")

    # Commit to make the new enum value available
    op.execute("COMMIT")

    # Create system user for API key executions
    op.execute(f"""
        INSERT INTO users (id, email, name, is_active, is_superuser, is_verified, is_registered, user_type)
        VALUES (
            '{SYSTEM_USER_ID}',
            'system@bifrost.local',
            'System',
            true,
            false,
            true,
            true,
            'SYSTEM'
        )
        ON CONFLICT (id) DO NOTHING
    """)

    # Add api_key_id column to executions table
    op.add_column(
        'executions',
        sa.Column('api_key_id', sa.UUID(), sa.ForeignKey('workflows.id'), nullable=True)
    )

    # Add index for efficient lookups by api_key_id
    op.create_index(
        'ix_executions_api_key',
        'executions',
        ['api_key_id'],
        postgresql_where=sa.text('api_key_id IS NOT NULL')
    )


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_executions_api_key', table_name='executions')

    # Drop api_key_id column
    op.drop_column('executions', 'api_key_id')

    # Delete system user
    op.execute(f"DELETE FROM users WHERE id = '{SYSTEM_USER_ID}'")

    # Note: Cannot remove enum value in PostgreSQL, so SYSTEM stays in user_type
