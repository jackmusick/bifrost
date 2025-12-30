"""
Event system ORM models.

Represents event sources (webhooks, schedules), subscriptions, events, and deliveries.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.enums import EventDeliveryStatus, EventSourceType, EventStatus
from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.executions import Execution
    from src.models.orm.integrations import Integration
    from src.models.orm.organizations import Organization
    from src.models.orm.workflows import Workflow


class EventSource(Base):
    """
    Event source registry.

    Represents a source of events that can trigger workflows.
    Can be a webhook endpoint, a schedule, or an internal event.
    """

    __tablename__ = "event_sources"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[EventSourceType] = mapped_column(
        PgEnum(
            "webhook",
            "schedule",
            "internal",
            name="event_source_type",
            create_type=False,
        ),
        nullable=False,
    )

    # Scope: NULL = global, otherwise org-specific
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), default=None
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    # Audit
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )

    # Relationships
    organization: Mapped["Organization | None"] = relationship(lazy="joined")
    webhook_source: Mapped["WebhookSource | None"] = relationship(
        back_populates="event_source",
        uselist=False,
        cascade="all, delete-orphan",
    )
    subscriptions: Mapped[list["EventSubscription"]] = relationship(
        back_populates="event_source",
        cascade="all, delete-orphan",
    )
    events: Mapped[list["Event"]] = relationship(
        back_populates="event_source",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_event_sources_organization_id", "organization_id"),
        Index("ix_event_sources_source_type", "source_type"),
        Index("ix_event_sources_is_active", "is_active"),
    )


class WebhookSource(Base):
    """
    Webhook-specific configuration for an event source.

    Contains adapter configuration, external subscription state,
    and callback URL information.
    """

    __tablename__ = "webhook_sources"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_source_id: Mapped[UUID] = mapped_column(
        ForeignKey("event_sources.id", ondelete="CASCADE"), nullable=False
    )

    # Adapter configuration
    adapter_name: Mapped[str | None] = mapped_column(
        String(100), default=None
    )  # NULL = generic
    integration_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("integrations.id", ondelete="SET NULL"), default=None
    )
    config: Mapped[dict] = mapped_column(JSONB, default=dict)

    # External subscription state (managed by adapter)
    external_id: Mapped[str | None] = mapped_column(
        String(255), default=None
    )  # Subscription ID from external service
    state: Mapped[dict] = mapped_column(
        JSONB, default=dict
    )  # Adapter-managed (secrets, tokens)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )

    # Relationships
    event_source: Mapped["EventSource"] = relationship(back_populates="webhook_source")
    integration: Mapped["Integration | None"] = relationship(lazy="joined")

    __table_args__ = (
        Index("ix_webhook_sources_event_source_id", "event_source_id"),
        Index("ix_webhook_sources_adapter_name", "adapter_name"),
        Index(
            "ix_webhook_sources_expires_at",
            "expires_at",
            postgresql_where=text("expires_at IS NOT NULL"),
        ),
    )


class EventSubscription(Base):
    """
    Subscription linking an event source to a workflow.

    When an event arrives at a source, all active subscriptions
    are evaluated and matching workflows are triggered.
    """

    __tablename__ = "event_subscriptions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_source_id: Mapped[UUID] = mapped_column(
        ForeignKey("event_sources.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )

    # Optional filtering
    event_type: Mapped[str | None] = mapped_column(
        String(255), default=None
    )  # e.g., "ticket.created"
    filter_expression: Mapped[str | None] = mapped_column(
        Text, default=None
    )  # JSONPath or simple expression (future)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Audit
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )

    # Relationships
    event_source: Mapped["EventSource"] = relationship(back_populates="subscriptions")
    workflow: Mapped["Workflow"] = relationship(lazy="joined")
    deliveries: Mapped[list["EventDelivery"]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_event_subscriptions_event_source_id", "event_source_id"),
        Index("ix_event_subscriptions_workflow_id", "workflow_id"),
        Index("ix_event_subscriptions_is_active", "is_active"),
        Index(
            "ix_event_subscriptions_unique_source_workflow",
            "event_source_id",
            "workflow_id",
            unique=True,
        ),
    )


class Event(Base):
    """
    Immutable event log.

    Records every event received from an event source.
    """

    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_source_id: Mapped[UUID] = mapped_column(
        ForeignKey("event_sources.id", ondelete="CASCADE"), nullable=False
    )

    # Event metadata
    event_type: Mapped[str | None] = mapped_column(
        String(255), default=None
    )  # e.g., "ticket.created"
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=text("NOW()")
    )

    # Payload
    headers: Mapped[dict | None] = mapped_column(JSONB, default=None)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Source metadata
    source_ip: Mapped[str | None] = mapped_column(String(45), default=None)  # IPv6 max

    # Processing status
    status: Mapped[EventStatus] = mapped_column(
        PgEnum(
            "received",
            "processing",
            "completed",
            "failed",
            name="event_status",
            create_type=False,
        ),
        default=EventStatus.RECEIVED,
    )

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=text("NOW()")
    )

    # Relationships
    event_source: Mapped["EventSource"] = relationship(back_populates="events")
    deliveries: Mapped[list["EventDelivery"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_events_event_source_id", "event_source_id"),
        Index("ix_events_received_at", "received_at"),
        Index("ix_events_status", "status"),
        Index("ix_events_event_type", "event_type"),
        # For cleanup job: events older than 30 days
        Index(
            "ix_events_created_at",
            "created_at",
        ),
    )


class EventDelivery(Base):
    """
    Delivery tracking for an event to a specific subscription.

    Tracks the status of delivering an event to a workflow,
    including execution results and retry information.
    """

    __tablename__ = "event_deliveries"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    event_subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("event_subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )

    # Execution reference (set when queued, before Execution record exists)
    # No FK constraint - Execution is created asynchronously by worker
    execution_id: Mapped[UUID | None] = mapped_column(default=None)

    # Delivery status
    status: Mapped[EventDeliveryStatus] = mapped_column(
        PgEnum(
            "pending",
            "queued",
            "success",
            "failed",
            "skipped",
            name="event_delivery_status",
            create_type=False,
        ),
        default=EventDeliveryStatus.PENDING,
    )
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    # Retry tracking (for future use)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, server_default=text("NOW()")
    )

    # Relationships
    event: Mapped["Event"] = relationship(back_populates="deliveries")
    subscription: Mapped["EventSubscription"] = relationship(back_populates="deliveries")
    workflow: Mapped["Workflow"] = relationship(lazy="joined")
    # No FK constraint on execution_id, so specify foreign_keys explicitly
    execution: Mapped["Execution | None"] = relationship(
        lazy="joined",
        foreign_keys=[execution_id],
        primaryjoin="EventDelivery.execution_id == Execution.id",
    )

    __table_args__ = (
        Index("ix_event_deliveries_event_id", "event_id"),
        Index("ix_event_deliveries_subscription_id", "event_subscription_id"),
        Index("ix_event_deliveries_workflow_id", "workflow_id"),
        Index("ix_event_deliveries_execution_id", "execution_id"),
        Index("ix_event_deliveries_status", "status"),
        # For cleanup job
        Index("ix_event_deliveries_created_at", "created_at"),
    )
