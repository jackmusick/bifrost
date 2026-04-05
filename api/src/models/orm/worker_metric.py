"""Worker metrics time-series data for diagnostics dashboard."""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.orm.base import Base


class WorkerMetric(Base):
    """Periodic resource snapshot from worker heartbeats."""

    __tablename__ = "worker_metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    worker_id: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )
    memory_current: Mapped[int] = mapped_column(BigInteger, nullable=False)
    memory_max: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fork_count: Mapped[int] = mapped_column(Integer, nullable=False)
    busy_count: Mapped[int] = mapped_column(Integer, nullable=False)
    idle_count: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index("ix_worker_metrics_timestamp", "timestamp"),
        Index("ix_worker_metrics_worker_timestamp", "worker_id", "timestamp"),
    )
