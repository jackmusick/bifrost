"""add_default_entity_id_to_integrations

Revision ID: 028071a17e8c
Revises: 5bcfc05cfeda
Create Date: 2025-12-23 15:59:22.881645+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '028071a17e8c'
down_revision: Union[str, None] = '5bcfc05cfeda'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('integrations', sa.Column('default_entity_id', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('integrations', 'default_entity_id')
