"""drop_redundant_root_layout_columns

Revision ID: 9e270d1bba50
Revises: fix_system_email_01
Create Date: 2026-01-17 00:44:12.997384+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9e270d1bba50'
down_revision: Union[str, None] = 'fix_system_email_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove redundant root_layout_type and root_layout_config columns.

    The layout information is now stored in the app_components table.
    The root layout container is the first component with parent_id=NULL.
    """
    op.drop_column('app_pages', 'root_layout_type')
    op.drop_column('app_pages', 'root_layout_config')


def downgrade() -> None:
    """Re-add root_layout_type and root_layout_config columns."""
    op.add_column(
        'app_pages',
        sa.Column('root_layout_type', sa.String(20), nullable=False, server_default="'column'")
    )
    op.add_column(
        'app_pages',
        sa.Column('root_layout_config', postgresql.JSONB(), nullable=False, server_default="{}")
    )
