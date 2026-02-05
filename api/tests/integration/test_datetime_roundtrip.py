"""
Integration tests to verify datetimes survive database roundtrips as naive UTC.
"""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.forms import Form
from src.models.orm.users import User


@pytest.mark.asyncio
async def test_form_datetime_roundtrip(db_session: AsyncSession):
    """Form created_at should be naive UTC after roundtrip."""
    # Create a form
    form = Form(
        id=uuid4(),
        name="Test Form",
        created_by="test@example.com",
    )
    db_session.add(form)
    await db_session.commit()

    # Retrieve it
    result = await db_session.execute(select(Form).where(Form.id == form.id))
    retrieved = result.scalar_one()

    # Verify datetime is naive (no timezone info)
    assert retrieved.created_at is not None
    assert retrieved.created_at.tzinfo is None, "created_at should be naive UTC"

    # Verify it's recent (within last minute)
    now = datetime.utcnow()
    assert now - retrieved.created_at < timedelta(minutes=1), "created_at should be recent"


@pytest.mark.asyncio
async def test_user_datetime_roundtrip(db_session: AsyncSession):
    """User timestamps should be naive UTC after roundtrip."""
    # Create a user
    user = User(
        id=uuid4(),
        email=f"test-{uuid4()}@example.com",
        name="Test User",
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.commit()

    # Retrieve it
    result = await db_session.execute(select(User).where(User.id == user.id))
    retrieved = result.scalar_one()

    # Verify datetimes are naive
    assert retrieved.created_at is not None
    assert retrieved.created_at.tzinfo is None, "created_at should be naive UTC"

    if retrieved.updated_at:
        assert retrieved.updated_at.tzinfo is None, "updated_at should be naive UTC"


@pytest.mark.asyncio
async def test_datetime_comparison_works(db_session: AsyncSession):
    """Naive UTC datetimes should be comparable without errors."""
    form1 = Form(
        id=uuid4(),
        name="Form 1",
        created_by="test@example.com",
    )
    db_session.add(form1)
    await db_session.flush()

    form2 = Form(
        id=uuid4(),
        name="Form 2",
        created_by="test@example.com",
    )
    db_session.add(form2)
    await db_session.commit()

    # Retrieve both
    result = await db_session.execute(select(Form).where(Form.id.in_([form1.id, form2.id])))
    forms = result.scalars().all()

    # Comparison should work without TypeError
    sorted_forms = sorted(forms, key=lambda f: f.created_at)
    assert len(sorted_forms) == 2
