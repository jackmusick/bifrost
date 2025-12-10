"""
GlobalBranding ORM model.

Represents global platform branding configuration.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, LargeBinary, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.orm.base import Base


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
