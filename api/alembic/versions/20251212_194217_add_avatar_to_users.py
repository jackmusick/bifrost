"""add_avatar_to_users

Revision ID: a5cd74106a68
Revises: 68515920579a
Create Date: 2025-12-12 19:42:17.343011+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5cd74106a68'
down_revision: Union[str, None] = '68515920579a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('avatar_data', sa.LargeBinary(), nullable=True))
    op.add_column('users', sa.Column('avatar_content_type', sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'avatar_content_type')
    op.drop_column('users', 'avatar_data')
