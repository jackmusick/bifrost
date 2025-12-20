"""Add passkeys table for WebAuthn authentication

Revision ID: 031_passkeys
Revises: 030_execution_messages
Create Date: 2025-12-20

This migration adds:
- webauthn_user_id column to users table (64-byte random identifier)
- user_passkeys table for storing WebAuthn credentials
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '60f0741b55d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add webauthn_user_id column to users table
    # This is a 64-byte random identifier used by WebAuthn
    op.add_column(
        'users',
        sa.Column('webauthn_user_id', sa.LargeBinary(64), nullable=True)
    )

    # Create user_passkeys table for WebAuthn credentials
    op.create_table(
        'user_passkeys',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),

        # WebAuthn credential data (required for verification)
        sa.Column('credential_id', sa.LargeBinary(), nullable=False),
        sa.Column('public_key', sa.LargeBinary(), nullable=False),
        sa.Column('sign_count', sa.Integer(), nullable=False, server_default='0'),

        # Credential metadata
        sa.Column('transports', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('device_type', sa.String(50), nullable=False),  # singleDevice, multiDevice
        sa.Column('backed_up', sa.Boolean(), nullable=False, server_default='false'),

        # User-facing info
        sa.Column('name', sa.String(255), nullable=False),  # "MacBook Pro Touch ID"
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),

        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('ix_user_passkeys_user_id', 'user_passkeys', ['user_id'])
    op.create_index('ix_user_passkeys_credential_id', 'user_passkeys', ['credential_id'], unique=True)


def downgrade() -> None:
    # Drop table and indexes
    op.drop_table('user_passkeys')

    # Remove webauthn_user_id from users
    op.drop_column('users', 'webauthn_user_id')
