"""
SQLAlchemy ORM Models for Bifrost

Pure database models using SQLAlchemy 2.0 declarative style.
These models define the database schema and relationships.

For API schemas (Create/Update/Public), see schemas.py
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum as SQLAlchemyEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.models.enums import (
    ConfigType,
    ExecutionStatus,
    FormAccessLevel,
    GitStatus,
    MFAMethodStatus,
    MFAMethodType,
    UserType,
)

if TYPE_CHECKING:
    pass


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


# =============================================================================
# Organization
# =============================================================================


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
    executions: Mapped[list["Execution"]] = relationship(back_populates="organization")
    configs: Mapped[list["Config"]] = relationship(back_populates="organization")
    system_configs: Mapped[list["SystemConfig"]] = relationship(
        back_populates="organization"
    )

    __table_args__ = (Index("ix_organizations_domain", "domain"),)


# =============================================================================
# User
# =============================================================================


class User(Base):
    """User database table."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str | None] = mapped_column(String(255), default=None)
    hashed_password: Mapped[str | None] = mapped_column(String(1024), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_registered: Mapped[bool] = mapped_column(Boolean, default=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_enforced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    user_type: Mapped[UserType] = mapped_column(
        SQLAlchemyEnum(
            UserType,
            name="user_type",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=UserType.ORG,
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), default=None
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime, default=None)
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
    organization: Mapped[Organization | None] = relationship(back_populates="users")
    roles: Mapped[list["UserRole"]] = relationship(back_populates="user")
    executions: Mapped[list["Execution"]] = relationship(
        back_populates="executed_by_user"
    )
    mfa_methods: Mapped[list["UserMFAMethod"]] = relationship(back_populates="user")
    recovery_codes: Mapped[list["MFARecoveryCode"]] = relationship(
        back_populates="user"
    )
    trusted_devices: Mapped[list["TrustedDevice"]] = relationship(back_populates="user")
    oauth_accounts: Mapped[list["UserOAuthAccount"]] = relationship(
        back_populates="user"
    )
    developer_context: Mapped["DeveloperContext | None"] = relationship(
        back_populates="user", uselist=False
    )
    developer_api_keys: Mapped[list["DeveloperApiKey"]] = relationship(
        back_populates="user"
    )

    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_organization_id", "organization_id"),
    )


# =============================================================================
# Role
# =============================================================================


class Role(Base):
    """Role database table."""

    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), default=None
    )
    created_by: Mapped[str] = mapped_column(String(255))
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
    users: Mapped[list["UserRole"]] = relationship(back_populates="role")

    __table_args__ = (Index("ix_roles_organization_id", "organization_id"),)


class UserRole(Base):
    """User-Role association table."""

    __tablename__ = "user_roles"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    assigned_by: Mapped[str] = mapped_column(String(255))
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="roles")
    role: Mapped[Role] = relationship(back_populates="users")


# =============================================================================
# Form
# =============================================================================


class FormField(Base):
    """Form field database table."""

    __tablename__ = "form_fields"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    form_id: Mapped[UUID] = mapped_column(
        ForeignKey("forms.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), default=None)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Optional field properties
    placeholder: Mapped[str | None] = mapped_column(String(500), default=None)
    help_text: Mapped[str | None] = mapped_column(Text, default=None)
    default_value: Mapped[dict | None] = mapped_column(JSONB, default=None)

    # For select/radio fields
    options: Mapped[dict | None] = mapped_column(JSONB, default=None)

    # For data provider integration
    data_provider: Mapped[str | None] = mapped_column(String(100), default=None)
    data_provider_inputs: Mapped[dict | None] = mapped_column(JSONB, default=None)

    # Advanced features
    visibility_expression: Mapped[str | None] = mapped_column(Text, default=None)
    validation: Mapped[dict | None] = mapped_column(JSONB, default=None)

    # For file fields
    allowed_types: Mapped[list | None] = mapped_column(ARRAY(Text), default=None)
    multiple: Mapped[bool | None] = mapped_column(Boolean, default=None)
    max_size_mb: Mapped[int | None] = mapped_column(Integer, default=None)

    # For markdown/html fields
    content: Mapped[str | None] = mapped_column(Text, default=None)

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
    form: Mapped["Form"] = relationship(back_populates="fields")


class Form(Base):
    """Form database table."""

    __tablename__ = "forms"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    workflow_id: Mapped[str | None] = mapped_column(String(255), default=None)
    default_launch_params: Mapped[dict | None] = mapped_column(JSONB, default=None)
    allowed_query_params: Mapped[list | None] = mapped_column(JSONB, default=None)
    access_level: Mapped[FormAccessLevel] = mapped_column(
        SQLAlchemyEnum(
            FormAccessLevel,
            name="form_access_level",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=FormAccessLevel.ROLE_BASED,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), default=None
    )
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )

    # Discovery metadata (synced from file watcher)
    file_path: Mapped[str | None] = mapped_column(String(1000), default=None)
    module_path: Mapped[str | None] = mapped_column(String(500), default=None)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    # Relationships
    organization: Mapped[Organization | None] = relationship(back_populates="forms")
    executions: Mapped[list["Execution"]] = relationship(back_populates="form")
    fields: Mapped[list["FormField"]] = relationship(
        back_populates="form",
        cascade="all, delete-orphan",
        order_by="FormField.position",
    )

    __table_args__ = (
        # Unique constraint on file_path (when not NULL) for ON CONFLICT upserts
        Index(
            "ix_forms_file_path_unique",
            "file_path",
            unique=True,
            postgresql_where=text("file_path IS NOT NULL"),
        ),
    )


class FormRole(Base):
    """Form-Role association table."""

    __tablename__ = "form_roles"

    form_id: Mapped[UUID] = mapped_column(ForeignKey("forms.id"), primary_key=True)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    assigned_by: Mapped[str] = mapped_column(String(255))
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )


# =============================================================================
# Execution
# =============================================================================


class Execution(Base):
    """Execution database table."""

    __tablename__ = "executions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workflow_name: Mapped[str] = mapped_column(String(255))
    workflow_version: Mapped[str | None] = mapped_column(String(50), default=None)
    status: Mapped[ExecutionStatus] = mapped_column(
        SQLAlchemyEnum(
            ExecutionStatus,
            name="execution_status",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=ExecutionStatus.PENDING,
    )
    parameters: Mapped[dict] = mapped_column(JSONB, default={})
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result_type: Mapped[str | None] = mapped_column(String(50), default=None)
    variables: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)

    # Resource metrics (captured from worker process)
    peak_memory_bytes: Mapped[int | None] = mapped_column(BigInteger, default=None)
    cpu_user_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    cpu_system_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    cpu_total_seconds: Mapped[float | None] = mapped_column(Float, default=None)

    executed_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    executed_by_name: Mapped[str] = mapped_column(String(255))
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), default=None
    )
    form_id: Mapped[UUID | None] = mapped_column(ForeignKey("forms.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )

    # Relationships
    executed_by_user: Mapped[User] = relationship(back_populates="executions")
    organization: Mapped[Organization | None] = relationship(
        back_populates="executions"
    )
    form: Mapped[Form | None] = relationship(back_populates="executions")
    logs: Mapped[list["ExecutionLog"]] = relationship(back_populates="execution")

    __table_args__ = (
        Index("ix_executions_org_status", "organization_id", "status"),
        Index("ix_executions_created", "created_at"),
        Index("ix_executions_user", "executed_by"),
        Index("ix_executions_workflow", "workflow_name"),
    )


class ExecutionLog(Base):
    """Execution log entries."""

    __tablename__ = "execution_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[UUID] = mapped_column(ForeignKey("executions.id"))
    level: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    log_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    execution: Mapped[Execution] = relationship(back_populates="logs")

    __table_args__ = (Index("ix_execution_logs_exec_seq", "execution_id", "sequence"),)


# =============================================================================
# Config
# =============================================================================


class Config(Base):
    """Configuration key-value store."""

    __tablename__ = "configs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(255))
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    config_type: Mapped[ConfigType] = mapped_column(
        SQLAlchemyEnum(
            ConfigType,
            name="config_type",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=ConfigType.STRING,
    )
    description: Mapped[str | None] = mapped_column(Text, default=None)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), default=None
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
    updated_by: Mapped[str] = mapped_column(String(255))

    # Relationships
    organization: Mapped[Organization | None] = relationship(back_populates="configs")

    __table_args__ = (
        Index("ix_configs_org_key", "organization_id", "key", unique=True),
    )


# =============================================================================
# Workflow Registry (persisted from file discovery)
# =============================================================================


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
        # Unique constraint on (file_path, function_name) for ON CONFLICT upserts
        UniqueConstraint("file_path", "function_name", name="workflows_file_function_key"),
    )


# =============================================================================
# Data Provider Registry (persisted from file discovery)
# =============================================================================


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


# =============================================================================
# Workflow Keys (REMOVED - migrated to workflows table)
# =============================================================================
#
# WorkflowKey table has been dropped. API keys are now stored directly
# on the workflows table using the following columns:
# - api_key_hash
# - api_key_description
# - api_key_enabled
# - api_key_created_by
# - api_key_created_at
# - api_key_last_used_at
# - api_key_expires_at
#
# See Workflow model above for the new structure.


# =============================================================================
# OAuth (for integrations)
# =============================================================================


class OAuthProvider(Base):
    """OAuth provider configuration."""

    __tablename__ = "oauth_providers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider_name: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    oauth_flow_type: Mapped[str] = mapped_column(
        String(50), default="authorization_code"
    )
    client_id: Mapped[str] = mapped_column(String(255))
    encrypted_client_secret: Mapped[bytes] = mapped_column(LargeBinary)
    authorization_url: Mapped[str | None] = mapped_column(String(500), default=None)
    token_url: Mapped[str | None] = mapped_column(String(500), default=None)
    scopes: Mapped[list] = mapped_column(JSONB, default=[])
    redirect_uri: Mapped[str | None] = mapped_column(String(500), default=None)
    status: Mapped[str] = mapped_column(String(50), default="not_connected")
    status_message: Mapped[str | None] = mapped_column(Text, default=None)
    last_token_refresh: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    provider_metadata: Mapped[dict] = mapped_column(JSONB, default={})
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), default=None
    )
    created_by: Mapped[str | None] = mapped_column(String(255), default=None)
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
    tokens: Mapped[list["OAuthToken"]] = relationship(back_populates="provider")

    __table_args__ = (
        Index(
            "ix_oauth_providers_org_name",
            "organization_id",
            "provider_name",
            unique=True,
        ),
    )


class OAuthToken(Base):
    """OAuth tokens for integration connections."""

    __tablename__ = "oauth_tokens"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), default=None
    )
    provider_id: Mapped[UUID] = mapped_column(ForeignKey("oauth_providers.id"))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), default=None)
    encrypted_access_token: Mapped[bytes] = mapped_column(LargeBinary)
    encrypted_refresh_token: Mapped[bytes | None] = mapped_column(
        LargeBinary, default=None
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    scopes: Mapped[list] = mapped_column(JSONB, default=[])
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
    provider: Mapped[OAuthProvider] = relationship(back_populates="tokens")


# =============================================================================
# Audit Log
# =============================================================================


class AuditLog(Base):
    """Audit log for tracking user actions."""

    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), default=None
    )
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), default=None)
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str | None] = mapped_column(String(100), default=None)
    resource_id: Mapped[UUID | None] = mapped_column(default=None)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), default=None)
    user_agent: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )

    __table_args__ = (
        Index("ix_audit_logs_org_time", "organization_id", "created_at"),
        Index("ix_audit_logs_user", "user_id"),
    )


# =============================================================================
# MFA
# =============================================================================


class UserMFAMethod(Base):
    """User MFA method enrollment."""

    __tablename__ = "user_mfa_methods"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    method_type: Mapped[MFAMethodType] = mapped_column(
        SQLAlchemyEnum(
            MFAMethodType,
            name="mfa_method_type",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        )
    )
    status: Mapped[MFAMethodStatus] = mapped_column(
        SQLAlchemyEnum(
            MFAMethodStatus,
            name="mfa_method_status",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=MFAMethodStatus.PENDING,
    )
    encrypted_secret: Mapped[str | None] = mapped_column(Text, default=None)
    mfa_metadata: Mapped[dict] = mapped_column(JSONB, default={})
    last_used_counter: Mapped[int | None] = mapped_column(Integer, default=None)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("NOW()")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="mfa_methods")

    __table_args__ = (
        Index("ix_user_mfa_methods_user_id", "user_id"),
        Index("ix_user_mfa_methods_user_status", "user_id", "status"),
    )


class MFARecoveryCode(Base):
    """MFA recovery codes."""

    __tablename__ = "mfa_recovery_codes"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    code_hash: Mapped[str] = mapped_column(String(255))
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    used_from_ip: Mapped[str | None] = mapped_column(String(45), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("NOW()")
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="recovery_codes")

    __table_args__ = (
        Index("ix_mfa_recovery_codes_user_id", "user_id"),
        Index("ix_mfa_recovery_codes_user_unused", "user_id", "is_used"),
    )


class TrustedDevice(Base):
    """Trusted devices that can bypass MFA."""

    __tablename__ = "trusted_devices"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    device_fingerprint: Mapped[str] = mapped_column(String(64))
    device_name: Mapped[str | None] = mapped_column(String(255), default=None)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_ip_address: Mapped[str | None] = mapped_column(String(45), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("NOW()")
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="trusted_devices")

    __table_args__ = (
        Index("ix_trusted_devices_user_id", "user_id"),
        Index(
            "ix_trusted_devices_fingerprint",
            "user_id",
            "device_fingerprint",
            unique=True,
        ),
    )


class UserOAuthAccount(Base):
    """Links OAuth accounts to users for SSO."""

    __tablename__ = "user_oauth_accounts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    provider_id: Mapped[str] = mapped_column(String(50))
    provider_user_id: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("NOW()")
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # Relationships
    user: Mapped[User] = relationship(back_populates="oauth_accounts")

    __table_args__ = (
        Index(
            "ix_user_oauth_provider_user",
            "provider_id",
            "provider_user_id",
            unique=True,
        ),
        Index("ix_user_oauth_user", "user_id"),
    )


# =============================================================================
# Global Branding
# =============================================================================


class GlobalBranding(Base):
    """Global platform branding configuration."""

    __tablename__ = "branding"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    square_logo_data: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)
    square_logo_content_type: Mapped[str | None] = mapped_column(
        String(50), default=None
    )
    rectangle_logo_data: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)
    rectangle_logo_content_type: Mapped[str | None] = mapped_column(
        String(50), default=None
    )
    primary_color: Mapped[str | None] = mapped_column(String(7), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )


# =============================================================================
# System Configuration
# =============================================================================


class SystemConfig(Base):
    """
    System-level configuration storage.

    Stores system settings like GitHub integration, branding assets, etc.
    Uses category+key for organization:
    - GitHub: category='github', key='integration'
    - Branding: category='branding', key='logo'

    value_json: For JSON config data
    value_bytes: For binary data (logos, files, etc.)

    Services handle their own encryption as needed.
    """

    __tablename__ = "system_configs"
    __table_args__ = (
        Index("ix_system_configs_category", "category"),
        Index("ix_system_configs_category_key", "category", "key"),
        Index("ix_system_configs_org_id", "organization_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    value_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
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
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    organization: Mapped["Organization | None"] = relationship(
        "Organization", back_populates="system_configs"
    )


# =============================================================================
# Platform Metrics
# =============================================================================


class ExecutionMetricsDaily(Base):
    """
    Daily aggregated execution metrics.

    Populated by the consumer on each execution completion.
    Used for trend charts and organization usage reports.
    """

    __tablename__ = "execution_metrics_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime] = mapped_column(Date, nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )

    # Execution counts
    execution_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    timeout_count: Mapped[int] = mapped_column(Integer, default=0)
    cancelled_count: Mapped[int] = mapped_column(Integer, default=0)

    # Duration metrics (milliseconds)
    total_duration_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    avg_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    max_duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    # Resource metrics
    total_memory_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    peak_memory_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    total_cpu_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    peak_cpu_seconds: Mapped[float] = mapped_column(Float, default=0.0)

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

    __table_args__ = (
        UniqueConstraint("date", "organization_id", name="uq_metrics_daily_date_org"),
        Index("ix_metrics_daily_date", "date"),
        Index("ix_metrics_daily_org", "organization_id"),
        # Partial unique index for global metrics (org_id IS NULL)
        # Enforces single global row per date
        Index(
            "uq_metrics_daily_date_global",
            "date",
            unique=True,
            postgresql_where=text("organization_id IS NULL"),
        ),
    )


class PlatformMetricsSnapshot(Base):
    """
    Current platform metrics snapshot.

    Refreshed periodically by the scheduler (every 1-5 minutes).
    Used for instant dashboard loads without expensive queries.
    Single row table - always id=1.
    """

    __tablename__ = "platform_metrics_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # Entity counts
    workflow_count: Mapped[int] = mapped_column(Integer, default=0)
    form_count: Mapped[int] = mapped_column(Integer, default=0)
    data_provider_count: Mapped[int] = mapped_column(Integer, default=0)
    organization_count: Mapped[int] = mapped_column(Integer, default=0)
    user_count: Mapped[int] = mapped_column(Integer, default=0)

    # Execution stats (all time)
    total_executions: Mapped[int] = mapped_column(Integer, default=0)
    total_success: Mapped[int] = mapped_column(Integer, default=0)
    total_failed: Mapped[int] = mapped_column(Integer, default=0)

    # Execution stats (last 24 hours)
    executions_24h: Mapped[int] = mapped_column(Integer, default=0)
    success_24h: Mapped[int] = mapped_column(Integer, default=0)
    failed_24h: Mapped[int] = mapped_column(Integer, default=0)

    # Current state
    running_count: Mapped[int] = mapped_column(Integer, default=0)
    pending_count: Mapped[int] = mapped_column(Integer, default=0)

    # Performance (last 24 hours)
    avg_duration_ms_24h: Mapped[int] = mapped_column(Integer, default=0)
    total_memory_bytes_24h: Mapped[int] = mapped_column(BigInteger, default=0)
    total_cpu_seconds_24h: Mapped[float] = mapped_column(Float, default=0.0)

    # Success rate
    success_rate_all_time: Mapped[float] = mapped_column(Float, default=0.0)
    success_rate_24h: Mapped[float] = mapped_column(Float, default=0.0)

    # Timestamp
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )


# =============================================================================
# Workspace Files (S3-based storage index)
# =============================================================================


class WorkspaceFile(Base):
    """
    Workspace file index for S3-based storage.

    This table indexes files stored in S3, enabling:
    - Fast file listing and search without S3 List operations
    - Git status tracking for each file
    - Content hash for change detection

    The actual file content is stored in S3 bucket: bifrost-{instance_id}-workspace
    """

    __tablename__ = "workspace_files"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100), default="text/plain")

    # Git sync status
    git_status: Mapped[GitStatus] = mapped_column(
        SQLAlchemyEnum(
            GitStatus,
            name="git_status",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=GitStatus.UNTRACKED,
    )
    last_git_commit_hash: Mapped[str | None] = mapped_column(String(40), default=None)

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

    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        # Unique constraint for ON CONFLICT upsert
        UniqueConstraint("path", name="uq_workspace_files_path"),
        # Index for path lookups (filtered for active files)
        Index(
            "ix_workspace_files_path",
            "path",
            postgresql_where=text("NOT is_deleted"),
        ),
        Index(
            "ix_workspace_files_git_status",
            "git_status",
            postgresql_where=text("NOT is_deleted"),
        ),
    )


# =============================================================================
# Developer Context (SDK configuration)
# =============================================================================


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
