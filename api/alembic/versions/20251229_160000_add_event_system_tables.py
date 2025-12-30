"""Add event system tables

Revision ID: e1e2e3e4e5e6
Revises: a1a14b958cf9
Create Date: 2025-12-29

This migration creates:
- event_sources table: Registry of event sources (webhooks, schedules, etc.)
- webhook_sources table: Webhook-specific configuration
- event_subscriptions table: Links event sources to workflows
- events table: Immutable event log
- event_deliveries table: Delivery tracking per subscription
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "e1e2e3e4e5e6"
down_revision: Union[str, None] = "a1a14b958cf9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types if they don't exist (using DO block for idempotency)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE event_source_type AS ENUM ('webhook', 'schedule', 'internal');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE event_status AS ENUM ('received', 'processing', 'completed', 'failed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE event_delivery_status AS ENUM ('pending', 'queued', 'success', 'failed', 'skipped');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$
    """)

    # Create event_sources table
    op.create_table(
        "event_sources",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "source_type",
            postgresql.ENUM(
                "webhook",
                "schedule",
                "internal",
                name="event_source_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_event_sources_organization_id", "event_sources", ["organization_id"]
    )
    op.create_index("ix_event_sources_source_type", "event_sources", ["source_type"])
    op.create_index("ix_event_sources_is_active", "event_sources", ["is_active"])

    # Create webhook_sources table
    op.create_table(
        "webhook_sources",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_source_id", UUID(as_uuid=True), nullable=False),
        sa.Column("adapter_name", sa.String(100), nullable=True),
        sa.Column("integration_id", UUID(as_uuid=True), nullable=True),
        sa.Column("config", JSONB(), nullable=False, server_default="{}"),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("state", JSONB(), nullable=False, server_default="{}"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["event_source_id"], ["event_sources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["integration_id"], ["integrations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_webhook_sources_event_source_id", "webhook_sources", ["event_source_id"]
    )
    op.create_index(
        "ix_webhook_sources_adapter_name", "webhook_sources", ["adapter_name"]
    )
    op.create_index(
        "ix_webhook_sources_expires_at",
        "webhook_sources",
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )

    # Create event_subscriptions table
    op.create_table(
        "event_subscriptions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_source_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(255), nullable=True),
        sa.Column("filter_expression", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["event_source_id"], ["event_sources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_event_subscriptions_event_source_id",
        "event_subscriptions",
        ["event_source_id"],
    )
    op.create_index(
        "ix_event_subscriptions_workflow_id", "event_subscriptions", ["workflow_id"]
    )
    op.create_index(
        "ix_event_subscriptions_is_active", "event_subscriptions", ["is_active"]
    )
    op.create_index(
        "ix_event_subscriptions_unique_source_workflow",
        "event_subscriptions",
        ["event_source_id", "workflow_id"],
        unique=True,
    )

    # Create events table
    op.create_table(
        "events",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_source_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(255), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("headers", JSONB(), nullable=True),
        sa.Column("data", JSONB(), nullable=False),
        sa.Column("source_ip", sa.String(45), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "received",
                "processing",
                "completed",
                "failed",
                name="event_status",
                create_type=False,
            ),
            nullable=False,
            server_default="received",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["event_source_id"], ["event_sources.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_events_event_source_id", "events", ["event_source_id"])
    op.create_index("ix_events_received_at", "events", ["received_at"])
    op.create_index("ix_events_status", "events", ["status"])
    op.create_index("ix_events_event_type", "events", ["event_type"])
    op.create_index("ix_events_created_at", "events", ["created_at"])

    # Create event_deliveries table
    op.create_table(
        "event_deliveries",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_subscription_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_id", UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "queued",
                "success",
                "failed",
                "skipped",
                name="event_delivery_status",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["event_subscription_id"], ["event_subscriptions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["executions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_event_deliveries_event_id", "event_deliveries", ["event_id"])
    op.create_index(
        "ix_event_deliveries_subscription_id",
        "event_deliveries",
        ["event_subscription_id"],
    )
    op.create_index(
        "ix_event_deliveries_workflow_id", "event_deliveries", ["workflow_id"]
    )
    op.create_index(
        "ix_event_deliveries_execution_id", "event_deliveries", ["execution_id"]
    )
    op.create_index("ix_event_deliveries_status", "event_deliveries", ["status"])
    op.create_index(
        "ix_event_deliveries_created_at", "event_deliveries", ["created_at"]
    )


def downgrade() -> None:
    # Drop event_deliveries table and indexes
    op.drop_index("ix_event_deliveries_created_at", table_name="event_deliveries")
    op.drop_index("ix_event_deliveries_status", table_name="event_deliveries")
    op.drop_index("ix_event_deliveries_execution_id", table_name="event_deliveries")
    op.drop_index("ix_event_deliveries_workflow_id", table_name="event_deliveries")
    op.drop_index("ix_event_deliveries_subscription_id", table_name="event_deliveries")
    op.drop_index("ix_event_deliveries_event_id", table_name="event_deliveries")
    op.drop_table("event_deliveries")

    # Drop events table and indexes
    op.drop_index("ix_events_created_at", table_name="events")
    op.drop_index("ix_events_event_type", table_name="events")
    op.drop_index("ix_events_status", table_name="events")
    op.drop_index("ix_events_received_at", table_name="events")
    op.drop_index("ix_events_event_source_id", table_name="events")
    op.drop_table("events")

    # Drop event_subscriptions table and indexes
    op.drop_index(
        "ix_event_subscriptions_unique_source_workflow",
        table_name="event_subscriptions",
    )
    op.drop_index("ix_event_subscriptions_is_active", table_name="event_subscriptions")
    op.drop_index(
        "ix_event_subscriptions_workflow_id", table_name="event_subscriptions"
    )
    op.drop_index(
        "ix_event_subscriptions_event_source_id", table_name="event_subscriptions"
    )
    op.drop_table("event_subscriptions")

    # Drop webhook_sources table and indexes
    op.drop_index("ix_webhook_sources_expires_at", table_name="webhook_sources")
    op.drop_index("ix_webhook_sources_adapter_name", table_name="webhook_sources")
    op.drop_index("ix_webhook_sources_event_source_id", table_name="webhook_sources")
    op.drop_table("webhook_sources")

    # Drop event_sources table and indexes
    op.drop_index("ix_event_sources_is_active", table_name="event_sources")
    op.drop_index("ix_event_sources_source_type", table_name="event_sources")
    op.drop_index("ix_event_sources_organization_id", table_name="event_sources")
    op.drop_table("event_sources")

    # Drop enum types (separate statements for asyncpg compatibility)
    op.execute("DROP TYPE IF EXISTS event_delivery_status")
    op.execute("DROP TYPE IF EXISTS event_status")
    op.execute("DROP TYPE IF EXISTS event_source_type")
