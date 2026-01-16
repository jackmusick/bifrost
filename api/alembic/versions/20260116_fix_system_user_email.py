"""fix_system_user_email

Update system user email from .local domain to valid domain.

The .local TLD is a special-use reserved name that Pydantic's EmailStr
validation rejects. This migration updates the system user email to use
a valid domain that passes email validation.

Revision ID: fix_system_email_01
Revises: 20260115_int_mapping
Create Date: 2026-01-16

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'fix_system_email_01'
down_revision: Union[str, None] = '20260115_int_mapping_nullable'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# System user UUID - well-known constant
SYSTEM_USER_ID = '00000000-0000-0000-0000-000000000001'
OLD_EMAIL = 'system@bifrost.local'
NEW_EMAIL = 'system@internal.gobifrost.com'


def upgrade() -> None:
    # Update system user email to valid domain
    op.execute(f"""
        UPDATE users
        SET email = '{NEW_EMAIL}'
        WHERE id = '{SYSTEM_USER_ID}' AND email = '{OLD_EMAIL}'
    """)


def downgrade() -> None:
    # Revert to old email (though .local will cause validation issues)
    op.execute(f"""
        UPDATE users
        SET email = '{OLD_EMAIL}'
        WHERE id = '{SYSTEM_USER_ID}' AND email = '{NEW_EMAIL}'
    """)
