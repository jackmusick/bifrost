"""Add workflow economics daily table

Revision ID: add_workflow_economics_daily
Revises: add_economics_to_metrics
Create Date: 2025-12-23

Creates workflow_economics_daily table for per-workflow per-org tracking:
- Daily aggregates of execution counts and economics metrics
- Tracks time saved and value generated per workflow
- Supports both organization-specific and global (platform) metrics
- Used for workflow-level reporting and analytics

Table structure:
- id: Serial primary key
- date: Date for the metrics
- workflow_id: UUID reference to workflows table
- organization_id: UUID reference to organizations table (nullable for global)
- execution_count: Total executions for the day
- success_count: Successful executions
- total_time_saved: Aggregated time saved in minutes
- total_value: Aggregated value generated
- created_at, updated_at: Timestamps

Unique constraint on (date, workflow_id, organization_id) ensures one row per day per workflow per org.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_workflow_economics_daily'
down_revision: Union[str, None] = 'add_economics_to_metrics'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create workflow_economics_daily table
    op.create_table(
        'workflow_economics_daily',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('workflow_id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=True),
        sa.Column('execution_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('success_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('total_time_saved', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('total_value', sa.Numeric(12, 2), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('date', 'workflow_id', 'organization_id', name='uq_workflow_economics_daily')
    )

    # Create indexes for efficient querying
    op.create_index('ix_workflow_economics_daily_date', 'workflow_economics_daily', ['date'])
    op.create_index('ix_workflow_economics_daily_workflow', 'workflow_economics_daily', ['workflow_id'])
    op.create_index('ix_workflow_economics_daily_org', 'workflow_economics_daily', ['organization_id'])

    # Create partial unique index for global metrics (org_id IS NULL)
    # Enforces single global row per date per workflow
    op.create_index(
        'uq_workflow_economics_daily_date_workflow_global',
        'workflow_economics_daily',
        ['date', 'workflow_id'],
        unique=True,
        postgresql_where=sa.text('organization_id IS NULL')
    )


def downgrade() -> None:
    op.drop_index('uq_workflow_economics_daily_date_workflow_global', table_name='workflow_economics_daily')
    op.drop_index('ix_workflow_economics_daily_org', table_name='workflow_economics_daily')
    op.drop_index('ix_workflow_economics_daily_workflow', table_name='workflow_economics_daily')
    op.drop_index('ix_workflow_economics_daily_date', table_name='workflow_economics_daily')
    op.drop_table('workflow_economics_daily')
