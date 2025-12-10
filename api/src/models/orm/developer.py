"""
Developer context and API key ORM models.

Represents developer configuration and API keys for SDK authentication.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.organizations import Organization
    from src.models.orm.users import User


class DeveloperContext(Base):
    """
    Developer context for SDK configuration.

    Stores per-user development settings used by the Bifrost SDK
    for local development and debugging.
    """

    __tablename__ = "developer_contexts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    # Context configuration
    default_org_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), default=None
    )
    default_parameters: Mapped[dict] = mapped_column(JSONB, default={})
    track_executions: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
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
    user: Mapped["User"] = relationship(back_populates="developer_context")
    default_org: Mapped["Organization | None"] = relationship()

    __table_args__ = (
        Index("ix_developer_contexts_user_id", "user_id"),
    )


class DeveloperApiKey(Base):
    """
    Developer API key for SDK authentication.

    These keys allow developers to authenticate their local SDK
    installations with the Bifrost API.
    """

    __tablename__ = "developer_api_keys"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    # Key identification
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(12), nullable=False)  # bfsk_xxxx
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)  # SHA-256

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    # Usage tracking
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    last_used_ip: Mapped[str | None] = mapped_column(String(45), default=None)
    use_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
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
    user: Mapped["User"] = relationship(back_populates="developer_api_keys")

    __table_args__ = (
        Index("ix_developer_api_keys_user_id", "user_id"),
        Index("ix_developer_api_keys_key_hash", "key_hash", unique=True),
        Index(
            "ix_developer_api_keys_active",
            "user_id",
            "is_active",
            postgresql_where=text("is_active = true"),
        ),
    )
