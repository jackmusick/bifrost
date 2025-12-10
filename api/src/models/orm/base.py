"""
Base declarative class for ORM models.

All SQLAlchemy models inherit from the Base class defined here.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass
