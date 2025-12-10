"""
WorkspaceFile ORM model.

Represents workspace file index for S3-based storage.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum as SQLAlchemyEnum, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.enums import GitStatus
from src.models.orm.base import Base


class WorkspaceFile(Base):
    """
    Workspace file index for S3-based storage.

    This table indexes files stored in S3, enabling:
    - Fast file listing and search without S3 List operations
    - Git status tracking for each file
    - Content hash for change detection

    The actual file content is stored in S3 bucket: bifrost-{instance_id}
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
