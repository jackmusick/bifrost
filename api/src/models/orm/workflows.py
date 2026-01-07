"""
Workflow ORM model.

Represents all executable user code (workflows, tools, data providers)
discovered from Python files. Data providers were consolidated into this
table in migration 20260103_000000.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.agents import Agent
    from src.models.orm.organizations import Organization


class Workflow(Base):
    """
    Workflow registry - persisted from file discovery.

    This table stores metadata for all executable user code discovered from
    Python files in the workspace. The discovery watcher syncs file changes
    to this table.

    Types:
    - workflow: Standard workflows (@workflow decorator)
    - tool: AI agent tools (@tool decorator)
    - data_provider: Data providers for forms/app builder (@data_provider decorator)
    """

    __tablename__ = "workflows"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), index=True)  # Display name (not unique)
    function_name: Mapped[str] = mapped_column(String(255))  # Actual Python function name
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[str] = mapped_column(String(100), default="General")

    # Type discriminator: 'workflow', 'tool', or 'data_provider'
    type: Mapped[str] = mapped_column(String(20), default="workflow", index=True)

    # Organization scoping - NULL means global (available to all orgs)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        index=True,
    )

    # File discovery metadata
    path: Mapped[str] = mapped_column(String(1000))  # Relative path from workspace root
    module_path: Mapped[str | None] = mapped_column(String(500), default=None)
    code: Mapped[str | None] = mapped_column(Text, default=None)  # Source code snapshot
    code_hash: Mapped[str | None] = mapped_column(String(64), default=None)  # SHA-256 of code
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
    execution_mode: Mapped[str] = mapped_column(String(20), default="async")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=1800)  # 30 min default

    # Tool configuration (for AI agent tool calling when type='tool')
    tool_description: Mapped[str | None] = mapped_column(Text, default=None)

    # Data provider configuration (when type='data_provider')
    cache_ttl_seconds: Mapped[int] = mapped_column(Integer, default=300)  # 5 min default

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
    organization: Mapped["Organization | None"] = relationship(
        back_populates="workflows",
        foreign_keys=[organization_id],
    )
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
        # Type index is created as a regular index via mapped_column(index=True)
        # Unique constraint on (path, function_name) for ON CONFLICT upserts
        UniqueConstraint("path", "function_name", name="workflows_path_function_key"),
    )


# ============================================================================
# DEPRECATED: DataProvider ORM model
# ============================================================================
# The DataProvider class below is DEPRECATED and will be removed after
# migration 20260103_000001 is applied. Data providers are now stored in
# the workflows table with type='data_provider'.
#
# During the transition period, this class is kept for backward compatibility
# with existing code that hasn't been updated yet.
# ============================================================================


class DataProvider(Base):
    """
    DEPRECATED: Data providers are now stored in the workflows table.

    This class is kept temporarily for backward compatibility during migration.
    Use Workflow with type='data_provider' instead.
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
