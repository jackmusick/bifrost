"""Rename economics to roi in workflow daily tracking

Revision ID: rename_economics_to_roi
Revises: add_workflow_economics_daily
Create Date: 2025-12-23

Renames workflow_economics_daily table and associated indexes/constraints to use "roi" terminology:
- workflow_economics_daily → workflow_roi_daily
- All associated indexes and constraints updated accordingly

This is a pure rename migration - no data or column structures are changed.
Column names (time_saved, value, etc.) remain unchanged as they are descriptive.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'rename_economics_to_roi'
down_revision: Union[str, None] = 'add_workflow_economics_daily'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename indexes first (must be done before table rename)
    op.execute('ALTER INDEX uq_workflow_economics_daily_date_workflow_global RENAME TO uq_workflow_roi_daily_date_workflow_global')
    op.execute('ALTER INDEX ix_workflow_economics_daily_date RENAME TO ix_workflow_roi_daily_date')
    op.execute('ALTER INDEX ix_workflow_economics_daily_workflow RENAME TO ix_workflow_roi_daily_workflow')
    op.execute('ALTER INDEX ix_workflow_economics_daily_org RENAME TO ix_workflow_roi_daily_org')

    # Rename constraint
    op.execute('ALTER TABLE workflow_economics_daily RENAME CONSTRAINT uq_workflow_economics_daily TO uq_workflow_roi_daily')

    # Rename table
    op.rename_table('workflow_economics_daily', 'workflow_roi_daily')


def downgrade() -> None:
    # Rename table back
    op.rename_table('workflow_roi_daily', 'workflow_economics_daily')

    # Rename constraint back
    op.execute('ALTER TABLE workflow_economics_daily RENAME CONSTRAINT uq_workflow_roi_daily TO uq_workflow_economics_daily')

    # Rename indexes back
    op.execute('ALTER INDEX ix_workflow_roi_daily_org RENAME TO ix_workflow_economics_daily_org')
    op.execute('ALTER INDEX ix_workflow_roi_daily_workflow RENAME TO ix_workflow_economics_daily_workflow')
    op.execute('ALTER INDEX ix_workflow_roi_daily_date RENAME TO ix_workflow_economics_daily_date')
    op.execute('ALTER INDEX uq_workflow_roi_daily_date_workflow_global RENAME TO uq_workflow_economics_daily_date_workflow_global')
