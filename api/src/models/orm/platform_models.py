"""
Platform model registry ORM models.

The `platform_models` table is a cache of the global model catalog. It is
populated by a background sync job that reads `api/shared/data/models.json`
(checked into the repo, kept fresh by a scheduled GitHub Action that pulls from
OpenRouter). Running installs refresh the table on an interval so new models
become available without a redeploy.

`org_model_aliases` and `model_deprecations` round out the resolver's lookup
chain (spec §5.8).
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.orm.base import Base


class PlatformModel(Base):
    """Cached row of the global model catalog (synced from models.json)."""

    __tablename__ = "platform_models"

    model_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    capabilities: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    cost_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    context_window: Mapped[int | None] = mapped_column(Integer, default=None)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    input_price_per_million: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), default=None)
    output_price_per_million: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), default=None)
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_platform_models_provider", "provider"),
        Index("ix_platform_models_cost_tier", "cost_tier"),
        Index("ix_platform_models_is_active", "is_active"),
    )


class OrgModelAlias(Base):
    """Per-org logical alias for a model (spec §5.8.1)."""

    __tablename__ = "org_model_aliases"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(100), nullable=False)
    target_model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)
    cost_tier: Mapped[str | None] = mapped_column(String(20), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "alias", name="uq_org_model_alias"),
        Index("ix_org_model_aliases_org", "organization_id"),
    )


class ModelDeprecation(Base):
    """Deprecation remap entries (spec §5.8.3).

    `organization_id` NULL = platform-wide entry (sourced from models.json);
    `organization_id` set = org admin override that wins over the platform entry.
    """

    __tablename__ = "model_deprecations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    old_model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    new_model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    deprecated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), default=None
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "old_model_id",
            "organization_id",
            name="uq_model_deprecation_old_org",
        ),
        Index("ix_model_deprecations_org", "organization_id"),
    )
