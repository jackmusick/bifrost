"""remove_event_delivery_execution_fk

Revision ID: dc862360f7cb
Revises: 0cde99f39214
Create Date: 2025-12-30 03:50:16.061770+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dc862360f7cb'
down_revision: Union[str, None] = '0cde99f39214'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove FK constraint - execution_id is a tracking reference only.
    # The Execution record is created asynchronously by the worker after
    # we store the execution_id on the delivery.
    op.drop_constraint(
        "event_deliveries_execution_id_fkey",
        "event_deliveries",
        type_="foreignkey"
    )


def downgrade() -> None:
    op.create_foreign_key(
        "event_deliveries_execution_id_fkey",
        "event_deliveries",
        "executions",
        ["execution_id"],
        ["id"],
        ondelete="SET NULL",
    )
