"""add_agent_system_tables

Revision ID: c0a523bf530f
Revises: 73275993f072
Create Date: 2025-12-18 14:35:14.692728+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ENUM


# revision identifiers, used by Alembic.
revision: str = 'c0a523bf530f'
down_revision: Union[str, None] = '73275993f072'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define PostgreSQL enums (create_type=False since we create them manually)
agent_access_level_enum = ENUM(
    'authenticated', 'role_based',
    name='agent_access_level',
    create_type=False
)
message_role_enum = ENUM(
    'user', 'assistant', 'system', 'tool',
    name='message_role',
    create_type=False
)


def table_exists(conn, table_name: str) -> bool:
    """Check if a table exists in the database."""
    result = conn.execute(
        sa.text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :name)"),
        {"name": table_name}
    )
    return result.scalar()


def index_exists(conn, index_name: str) -> bool:
    """Check if an index exists in the database."""
    result = conn.execute(
        sa.text("SELECT EXISTS (SELECT FROM pg_indexes WHERE indexname = :name)"),
        {"name": index_name}
    )
    return result.scalar()


def column_exists(conn, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    result = conn.execute(
        sa.text("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = :table AND column_name = :column
            )
        """),
        {"table": table_name, "column": column_name}
    )
    return result.scalar()


def upgrade() -> None:
    conn = op.get_bind()

    # Create agent_access_level enum (idempotent - skip if exists)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE agent_access_level AS ENUM ('authenticated', 'role_based');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # Create message_role enum (idempotent - skip if exists)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system', 'tool');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # Create agents table
    if not table_exists(conn, 'agents'):
        op.create_table(
            'agents',
            sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('system_prompt', sa.Text(), nullable=False),
            sa.Column('channels', JSONB(), nullable=False, server_default='["chat"]'),
            sa.Column('access_level', agent_access_level_enum, nullable=False, server_default='role_based'),
            sa.Column('organization_id', sa.UUID(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('file_path', sa.String(1000), nullable=True),
            sa.Column('created_by', sa.String(255), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        )

    # Create indexes for agents table (idempotent)
    if not index_exists(conn, 'ix_agents_file_path_unique'):
        op.create_index(
            'ix_agents_file_path_unique',
            'agents',
            ['file_path'],
            unique=True,
            postgresql_where=sa.text('file_path IS NOT NULL')
        )
    if not index_exists(conn, 'ix_agents_organization_id'):
        op.create_index('ix_agents_organization_id', 'agents', ['organization_id'])
    if not index_exists(conn, 'ix_agents_is_active'):
        op.create_index('ix_agents_is_active', 'agents', ['is_active'])

    # Create agent_tools junction table
    if not table_exists(conn, 'agent_tools'):
        op.create_table(
            'agent_tools',
            sa.Column('agent_id', sa.UUID(), nullable=False),
            sa.Column('workflow_id', sa.UUID(), nullable=False),
            sa.PrimaryKeyConstraint('agent_id', 'workflow_id'),
            sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
        )

    # Create agent_delegations junction table
    if not table_exists(conn, 'agent_delegations'):
        op.create_table(
            'agent_delegations',
            sa.Column('parent_agent_id', sa.UUID(), nullable=False),
            sa.Column('child_agent_id', sa.UUID(), nullable=False),
            sa.PrimaryKeyConstraint('parent_agent_id', 'child_agent_id'),
            sa.ForeignKeyConstraint(['parent_agent_id'], ['agents.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['child_agent_id'], ['agents.id'], ondelete='CASCADE'),
        )

    # Create agent_roles junction table
    if not table_exists(conn, 'agent_roles'):
        op.create_table(
            'agent_roles',
            sa.Column('agent_id', sa.UUID(), nullable=False),
            sa.Column('role_id', sa.UUID(), nullable=False),
            sa.Column('assigned_by', sa.String(255), nullable=False),
            sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.PrimaryKeyConstraint('agent_id', 'role_id'),
            sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        )

    # Create conversations table
    if not table_exists(conn, 'conversations'):
        op.create_table(
            'conversations',
            sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
            sa.Column('agent_id', sa.UUID(), nullable=False),
            sa.Column('user_id', sa.UUID(), nullable=False),
            sa.Column('channel', sa.String(50), nullable=False, server_default='chat'),
            sa.Column('title', sa.String(500), nullable=True),
            sa.Column('extra_data', JSONB(), nullable=False, server_default='{}'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['agent_id'], ['agents.id']),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        )

    # Create indexes for conversations table (idempotent)
    if not index_exists(conn, 'ix_conversations_user_id'):
        op.create_index('ix_conversations_user_id', 'conversations', ['user_id'])
    if not index_exists(conn, 'ix_conversations_agent_id'):
        op.create_index('ix_conversations_agent_id', 'conversations', ['agent_id'])
    if not index_exists(conn, 'ix_conversations_created_at'):
        op.create_index('ix_conversations_created_at', 'conversations', ['created_at'])

    # Create messages table
    if not table_exists(conn, 'messages'):
        op.create_table(
            'messages',
            sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
            sa.Column('conversation_id', sa.UUID(), nullable=False),
            sa.Column('role', message_role_enum, nullable=False),
            sa.Column('content', sa.Text(), nullable=True),
            sa.Column('tool_calls', JSONB(), nullable=True),
            sa.Column('tool_call_id', sa.String(255), nullable=True),
            sa.Column('tool_name', sa.String(255), nullable=True),
            sa.Column('token_count_input', sa.Integer(), nullable=True),
            sa.Column('token_count_output', sa.Integer(), nullable=True),
            sa.Column('model', sa.String(100), nullable=True),
            sa.Column('duration_ms', sa.Integer(), nullable=True),
            sa.Column('sequence', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        )

    # Create index for messages table (idempotent)
    if not index_exists(conn, 'ix_messages_conversation_sequence'):
        op.create_index('ix_messages_conversation_sequence', 'messages', ['conversation_id', 'sequence'])

    # Add is_tool and tool_description to workflows table (idempotent)
    if not column_exists(conn, 'workflows', 'is_tool'):
        op.add_column('workflows', sa.Column('is_tool', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    if not column_exists(conn, 'workflows', 'tool_description'):
        op.add_column('workflows', sa.Column('tool_description', sa.Text(), nullable=True))
    if not index_exists(conn, 'ix_workflows_is_tool'):
        op.create_index('ix_workflows_is_tool', 'workflows', ['is_tool'], postgresql_where=sa.text('is_tool = true'))


def downgrade() -> None:
    conn = op.get_bind()

    # Remove workflow columns
    if index_exists(conn, 'ix_workflows_is_tool'):
        op.drop_index('ix_workflows_is_tool', table_name='workflows')
    if column_exists(conn, 'workflows', 'tool_description'):
        op.drop_column('workflows', 'tool_description')
    if column_exists(conn, 'workflows', 'is_tool'):
        op.drop_column('workflows', 'is_tool')

    # Drop messages table
    if table_exists(conn, 'messages'):
        if index_exists(conn, 'ix_messages_conversation_sequence'):
            op.drop_index('ix_messages_conversation_sequence', table_name='messages')
        op.drop_table('messages')

    # Drop conversations table
    if table_exists(conn, 'conversations'):
        if index_exists(conn, 'ix_conversations_created_at'):
            op.drop_index('ix_conversations_created_at', table_name='conversations')
        if index_exists(conn, 'ix_conversations_agent_id'):
            op.drop_index('ix_conversations_agent_id', table_name='conversations')
        if index_exists(conn, 'ix_conversations_user_id'):
            op.drop_index('ix_conversations_user_id', table_name='conversations')
        op.drop_table('conversations')

    # Drop agent_roles table
    if table_exists(conn, 'agent_roles'):
        op.drop_table('agent_roles')

    # Drop agent_delegations table
    if table_exists(conn, 'agent_delegations'):
        op.drop_table('agent_delegations')

    # Drop agent_tools table
    if table_exists(conn, 'agent_tools'):
        op.drop_table('agent_tools')

    # Drop agents table
    if table_exists(conn, 'agents'):
        if index_exists(conn, 'ix_agents_is_active'):
            op.drop_index('ix_agents_is_active', table_name='agents')
        if index_exists(conn, 'ix_agents_organization_id'):
            op.drop_index('ix_agents_organization_id', table_name='agents')
        if index_exists(conn, 'ix_agents_file_path_unique'):
            op.drop_index('ix_agents_file_path_unique', table_name='agents')
        op.drop_table('agents')

    # Drop enums (idempotent)
    op.execute("DROP TYPE IF EXISTS message_role")
    op.execute("DROP TYPE IF EXISTS agent_access_level")
