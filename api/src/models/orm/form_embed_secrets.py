"""ORM model for form embed secrets."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.orm.base import Base


class FormEmbedSecret(Base):
    """Shared secret for HMAC-authenticated iframe embedding of forms."""

    __tablename__ = "form_embed_secrets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    form_id: Mapped[UUID] = mapped_column(
        ForeignKey("forms.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )

    form = relationship("Form", back_populates="embed_secrets")

    __table_args__ = (
        Index("ix_form_embed_secrets_form_id", "form_id"),
    )
