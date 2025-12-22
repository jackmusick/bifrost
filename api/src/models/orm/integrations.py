"""
Integration and IntegrationMapping ORM models.

Represents integrations (OAuth providers, data providers, configurations)
and their mappings to organizations with external entities.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.oauth import OAuthProvider, OAuthToken
    from src.models.orm.organizations import Organization


class Integration(Base):
    """Integration configuration and metadata.

    Represents an integration (e.g., "Microsoft Partner", "QuickBooks Online")
    with optional OAuth provider, data provider for entity listing, and
    configuration schema for available settings.
    """

    __tablename__ = "integrations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    list_entities_data_provider_id: Mapped[UUID | None] = mapped_column(
        default=None, nullable=True
    )
    config_schema: Mapped[dict | None] = mapped_column(JSONB, default=None, nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(255), default=None, nullable=True)
    entity_id_name: Mapped[str | None] = mapped_column(String(255), default=None, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )

    # Relationships
    oauth_provider: Mapped["OAuthProvider | None"] = relationship(
        back_populates="integration",
        lazy="joined",
    )
    mappings: Mapped[list["IntegrationMapping"]] = relationship(
        back_populates="integration",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_integrations_name", "name"),
    )

    @property
    def has_oauth_config(self) -> bool:
        """Check if OAuth is configured for this integration."""
        return self.oauth_provider is not None


class IntegrationMapping(Base):
    """Integration mapping to an organization and external entity.

    Maps an integration to an organization with a specific external entity
    (e.g., tenant ID, company ID) and optional per-org OAuth token override.
    """

    __tablename__ = "integration_mappings"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    integration_id: Mapped[UUID] = mapped_column(
        ForeignKey("integrations.id"), nullable=False
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_name: Mapped[str | None] = mapped_column(String(255), default=None, nullable=True)
    oauth_token_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("oauth_tokens.id"), default=None, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )

    # Relationships
    integration: Mapped["Integration"] = relationship(
        back_populates="mappings",
        lazy="joined",
    )
    organization: Mapped["Organization"] = relationship(
        lazy="joined",
    )
    oauth_token: Mapped["OAuthToken | None"] = relationship(
        "OAuthToken",
        foreign_keys=[oauth_token_id],
        lazy="joined",
    )

    __table_args__ = (
        Index("ix_integration_mappings_integration_id", "integration_id"),
        Index("ix_integration_mappings_organization_id", "organization_id"),
        Index("ix_integration_mappings_oauth_token_id", "oauth_token_id"),
        Index(
            "ix_integration_mappings_unique_per_org",
            "integration_id",
            "organization_id",
            unique=True,
        ),
    )
