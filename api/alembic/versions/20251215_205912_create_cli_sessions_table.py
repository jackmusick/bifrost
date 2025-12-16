"""create_cli_sessions_table

Revision ID: 73275993f072
Revises: aec8b0bd248d
Create Date: 2025-12-15 20:59:12.261793+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '73275993f072'
down_revision: Union[str, None] = 'aec8b0bd248d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create cli_sessions table
    op.create_table(
        'cli_sessions',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=False),
        sa.Column('workflows', sa.JSON(), nullable=False),
        sa.Column('selected_workflow', sa.Text(), nullable=True),
        sa.Column('params', sa.JSON(), nullable=True),
        sa.Column('pending', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_cli_sessions_user_id', 'cli_sessions', ['user_id'])

    # Add session_id to executions table
    op.add_column('executions', sa.Column('session_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_executions_session_id',
        'executions',
        'cli_sessions',
        ['session_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index('idx_executions_session_id', 'executions', ['session_id'])


def downgrade() -> None:
    # Remove session_id from executions
    op.drop_index('idx_executions_session_id', table_name='executions')
    op.drop_constraint('fk_executions_session_id', 'executions', type_='foreignkey')
    op.drop_column('executions', 'session_id')

    # Drop cli_sessions table
    op.drop_index('idx_cli_sessions_user_id', table_name='cli_sessions')
    op.drop_table('cli_sessions')
