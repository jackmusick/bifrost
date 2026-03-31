"""Add ondelete cascades for user foreign keys

Revision ID: 20260331_user_fk_cascades
Revises: 20260326_drop_agent_is_system
Create Date: 2026-03-31

Ensure deleting a user doesn't 500 due to FK constraint violations.
- CASCADE: user_roles, mfa tables, conversations (owned by user)
- SET NULL: executions, agents, audit, oauth, schedules, etc. (preserve history)
"""
from alembic import op

revision = "20260331_user_fk_cascades"
down_revision = "20260326_drop_agent_is_system"
branch_labels = None
depends_on = None

# (constraint_name, table, column, ref_column, ondelete, make_nullable)
_FK_UPDATES = [
    # CASCADE — delete child rows when user is deleted
    ("user_roles_user_id_fkey", "user_roles", "user_id", "id", "CASCADE", False),
    ("user_mfa_methods_user_id_fkey", "user_mfa_methods", "user_id", "id", "CASCADE", False),
    ("mfa_recovery_codes_user_id_fkey", "mfa_recovery_codes", "user_id", "id", "CASCADE", False),
    ("trusted_devices_user_id_fkey", "trusted_devices", "user_id", "id", "CASCADE", False),
    ("user_oauth_accounts_user_id_fkey", "user_oauth_accounts", "user_id", "id", "CASCADE", False),
    ("user_passkeys_user_id_fkey", "user_passkeys", "user_id", "id", "CASCADE", False),
    ("conversations_user_id_fkey", "conversations", "user_id", "id", "CASCADE", False),
    # SET NULL — preserve history, clear user reference
    ("executions_executed_by_fkey", "executions", "executed_by", "id", "SET NULL", True),
    ("agents_owner_user_id_fkey", "agents", "owner_user_id", "id", "SET NULL", False),
    ("audit_logs_user_id_fkey", "audit_logs", "user_id", "id", "SET NULL", False),
    ("oauth_tokens_user_id_fkey", "oauth_tokens", "user_id", "id", "SET NULL", False),
    ("schedules_created_by_fkey", "schedules", "created_by", "id", "SET NULL", False),
    ("system_logs_executed_by_fkey", "system_logs", "executed_by", "id", "SET NULL", False),
]


def upgrade() -> None:
    for constraint, table, column, ref_col, ondelete, make_nullable in _FK_UPDATES:
        if make_nullable:
            op.alter_column(table, column, nullable=True)

        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(
            constraint, table, "users", [column], [ref_col], ondelete=ondelete,
        )


def downgrade() -> None:
    for constraint, table, column, ref_col, _ondelete, make_nullable in reversed(_FK_UPDATES):
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(
            constraint, table, "users", [column], [ref_col],
        )
        if make_nullable:
            op.alter_column(table, column, nullable=False)
