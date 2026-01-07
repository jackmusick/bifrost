"""
User, Role, and UserRole ORM models.

Represents users, roles, and role assignments in the platform.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum as SQLAlchemyEnum, ForeignKey, Index, LargeBinary, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.enums import UserType
from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.agents import Agent
    from src.models.orm.developer import DeveloperContext
    from src.models.orm.executions import Execution
    from src.models.orm.mfa import MFARecoveryCode, TrustedDevice, UserMFAMethod, UserOAuthAccount, UserPasskey
    from src.models.orm.organizations import Organization


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
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
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

    # Avatar
    avatar_data: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)
    avatar_content_type: Mapped[str | None] = mapped_column(String(50), default=None)

    # WebAuthn/Passkeys
    webauthn_user_id: Mapped[bytes | None] = mapped_column(LargeBinary(64), default=None)

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="users")
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
    passkeys: Mapped[list["UserPasskey"]] = relationship(back_populates="user")
    developer_context: Mapped["DeveloperContext | None"] = relationship(
        back_populates="user", uselist=False
    )

    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_organization_id", "organization_id"),
    )


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
    # Agents via junction table
    agents: Mapped[list["Agent"]] = relationship(
        secondary="agent_roles",
        back_populates="roles",
    )

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
    user: Mapped["User"] = relationship(back_populates="roles")
    role: Mapped["Role"] = relationship(back_populates="users")
