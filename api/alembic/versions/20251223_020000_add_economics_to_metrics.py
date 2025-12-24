"""Add economics columns to metrics tables

Revision ID: add_economics_to_metrics
Revises: add_workflow_economics
Create Date: 2025-12-23

Adds economics aggregation columns to metrics tables:

execution_metrics_daily:
- total_time_saved: Aggregated time saved in minutes (BigInteger)
- total_value: Aggregated value (Numeric(12,2))

platform_metrics_snapshot:
- time_saved_24h: Time saved in last 24 hours (BigInteger)
- value_24h: Value generated in last 24 hours (Numeric(12,2))
- time_saved_all_time: Total time saved all time (BigInteger)
- value_all_time: Total value all time (Numeric(12,2))

executions:
- time_saved: Final time_saved value for this execution (Integer)
- value: Final value for this execution (Numeric(10,2))

These columns enable economic impact tracking and reporting.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_economics_to_metrics'
down_revision: Union[str, None] = 'add_workflow_economics'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add economics columns to execution_metrics_daily
    op.add_column(
        'execution_metrics_daily',
        sa.Column('total_time_saved', sa.BigInteger(), server_default='0', nullable=False)
    )
    op.add_column(
        'execution_metrics_daily',
        sa.Column('total_value', sa.Numeric(12, 2), server_default='0', nullable=False)
    )

    # Add economics columns to platform_metrics_snapshot
    op.add_column(
        'platform_metrics_snapshot',
        sa.Column('time_saved_24h', sa.BigInteger(), server_default='0', nullable=False)
    )
    op.add_column(
        'platform_metrics_snapshot',
        sa.Column('value_24h', sa.Numeric(12, 2), server_default='0', nullable=False)
    )
    op.add_column(
        'platform_metrics_snapshot',
        sa.Column('time_saved_all_time', sa.BigInteger(), server_default='0', nullable=False)
    )
    op.add_column(
        'platform_metrics_snapshot',
        sa.Column('value_all_time', sa.Numeric(12, 2), server_default='0', nullable=False)
    )

    # Add economics columns to executions table
    op.add_column(
        'executions',
        sa.Column('time_saved', sa.Integer(), server_default='0', nullable=False)
    )
    op.add_column(
        'executions',
        sa.Column('value', sa.Numeric(10, 2), server_default='0', nullable=False)
    )


def downgrade() -> None:
    # Drop executions economics columns
    op.drop_column('executions', 'value')
    op.drop_column('executions', 'time_saved')

    # Drop platform_metrics_snapshot economics columns
    op.drop_column('platform_metrics_snapshot', 'value_all_time')
    op.drop_column('platform_metrics_snapshot', 'time_saved_all_time')
    op.drop_column('platform_metrics_snapshot', 'value_24h')
    op.drop_column('platform_metrics_snapshot', 'time_saved_24h')

    # Drop execution_metrics_daily economics columns
    op.drop_column('execution_metrics_daily', 'total_value')
    op.drop_column('execution_metrics_daily', 'total_time_saved')
