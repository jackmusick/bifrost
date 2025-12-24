"""Merge passkeys and integrations branches

Revision ID: f6g7h8i9j0k1
Revises: a1b2c3d4e5f6, e5f6g7h8i9j0
Create Date: 2025-12-21

This migration merges the parallel development branches:
- passkeys branch (a1b2c3d4e5f6)
- integrations branch (e5f6g7h8i9j0)
"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = 'f6g7h8i9j0k1'
down_revision: tuple[str, str] = ('a1b2c3d4e5f6', 'e5f6g7h8i9j0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Merge migration - no schema changes needed
    pass


def downgrade() -> None:
    # Merge migration - no schema changes needed
    pass
