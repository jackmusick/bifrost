"""
Workflow and DataProvider ORM models.

Represents workflows and data providers discovered from Python files.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.agents import Agent


class Workflow(Base):
    """
    Workflow registry - persisted from file discovery.

    This table stores workflow metadata discovered from Python files in the
    workspace. The discovery watcher syncs file changes to this table.
    """

    __tablename__ = "workflows"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), index=True)  # Display name (not unique)
    function_name: Mapped[str] = mapped_column(String(255))  # Actual Python function name
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[str] = mapped_column(String(100), default="General")

    # File discovery metadata
    file_path: Mapped[str] = mapped_column(String(1000))
    module_path: Mapped[str | None] = mapped_column(String(500), default=None)
    schedule: Mapped[str | None] = mapped_column(
        String(100), default=None
    )  # CRON expression
    parameters_schema: Mapped[list] = mapped_column(JSONB, default=[])
    tags: Mapped[list] = mapped_column(JSONB, default=[])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    # Endpoint configuration
    endpoint_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_methods: Mapped[list] = mapped_column(JSONB, default=["POST"])
    execution_mode: Mapped[str] = mapped_column(String(20), default="sync")

    # Tool configuration (for AI agent tool calling)
    is_tool: Mapped[bool] = mapped_column(Boolean, default=False)
    tool_description: Mapped[str | None] = mapped_column(Text, default=None)

    # Economics - value metrics for reporting
    time_saved: Mapped[int] = mapped_column(Integer, default=0)  # Minutes saved per execution
    value: Mapped[float] = mapped_column(Numeric(10, 2), default=0)  # Flexible value unit

    # API key (one per workflow, replaces workflow_keys table)
    api_key_hash: Mapped[str | None] = mapped_column(
        String(64), default=None
    )  # SHA-256 hash
    api_key_description: Mapped[str | None] = mapped_column(Text, default=None)
    api_key_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    api_key_created_by: Mapped[str | None] = mapped_column(String(255), default=None)
    api_key_created_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    api_key_last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None
    )
    api_key_expires_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

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
    agents: Mapped[list["Agent"]] = relationship(
        secondary="agent_tools",
        back_populates="tools",
    )

    __table_args__ = (
        Index(
            "ix_workflows_schedule",
            "schedule",
            postgresql_where=text("schedule IS NOT NULL"),
        ),
        Index(
            "ix_workflows_api_key_hash",
            "api_key_hash",
            postgresql_where=text("api_key_hash IS NOT NULL"),
        ),
        Index(
            "ix_workflows_is_tool",
            "is_tool",
            postgresql_where=text("is_tool = true"),
        ),
        # Unique constraint on (file_path, function_name) for ON CONFLICT upserts
        UniqueConstraint("file_path", "function_name", name="workflows_file_function_key"),
    )


class DataProvider(Base):
    """
    Data provider registry - persisted from file discovery.

    This table stores data provider metadata discovered from Python files
    in the workspace. The discovery watcher syncs file changes to this table.
    """

    __tablename__ = "data_providers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), index=True)  # Display name (not unique)
    function_name: Mapped[str] = mapped_column(String(255))  # Actual Python function name
    description: Mapped[str | None] = mapped_column(Text, default=None)
    file_path: Mapped[str] = mapped_column(String(1000))
    module_path: Mapped[str | None] = mapped_column(String(500), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        # Unique constraint on (file_path, function_name) for ON CONFLICT upserts
        UniqueConstraint("file_path", "function_name", name="data_providers_file_function_key"),
    )
