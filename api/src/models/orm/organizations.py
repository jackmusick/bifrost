"""
Organization ORM model.

Represents tenant organizations in the Bifrost platform.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.agents import Agent
    from src.models.orm.config import Config, SystemConfig
    from src.models.orm.executions import Execution
    from src.models.orm.forms import Form
    from src.models.orm.knowledge import KnowledgeStore
    from src.models.orm.metrics import KnowledgeStorageDaily
    from src.models.orm.tables import Table
    from src.models.orm.users import User


class Organization(Base):
    """Organization database table."""

    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255))
    domain: Mapped[str | None] = mapped_column(String(255), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    settings: Mapped[dict] = mapped_column(JSONB, default={})
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )
    created_by: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )

    # Relationships
    users: Mapped[list["User"]] = relationship(back_populates="organization")
    forms: Mapped[list["Form"]] = relationship(back_populates="organization")
    agents: Mapped[list["Agent"]] = relationship(back_populates="organization")
    executions: Mapped[list["Execution"]] = relationship(back_populates="organization")
    configs: Mapped[list["Config"]] = relationship(back_populates="organization")
    system_configs: Mapped[list["SystemConfig"]] = relationship(
        back_populates="organization"
    )
    knowledge_entries: Mapped[list["KnowledgeStore"]] = relationship(
        back_populates="organization"
    )
    knowledge_storage_snapshots: Mapped[list["KnowledgeStorageDaily"]] = relationship(
        back_populates="organization"
    )
    tables: Mapped[list["Table"]] = relationship(back_populates="organization")

    __table_args__ = (Index("ix_organizations_domain", "domain"),)
