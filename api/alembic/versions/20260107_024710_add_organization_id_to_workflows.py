"""add_organization_id_to_workflows

Revision ID: 04d2e6fc1522
Revises: b4ad64a97000
Create Date: 2026-01-07 02:47:10.450316+00:00

Adds organization scoping to workflows:
- Workflows with organization_id = NULL are global (available to all orgs)
- Workflows with organization_id set are org-scoped (only visible to that org + global)
- Existing workflows remain global (no data migration needed)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '04d2e6fc1522'
down_revision: Union[str, None] = 'b4ad64a97000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add organization_id column to workflows table
    op.add_column(
        'workflows',
        sa.Column(
            'organization_id',
            sa.UUID(),
            sa.ForeignKey('organizations.id', ondelete='SET NULL'),
            nullable=True,
        )
    )

    # Create index for efficient org filtering
    op.create_index(
        'ix_workflows_organization_id',
        'workflows',
        ['organization_id']
    )


def downgrade() -> None:
    # Drop index first
    op.drop_index('ix_workflows_organization_id', table_name='workflows')

    # Drop column
    op.drop_column('workflows', 'organization_id')
