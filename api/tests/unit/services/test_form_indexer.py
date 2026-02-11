"""Unit tests for FormIndexer."""

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.forms import Form, FormField
from src.services.file_storage.indexers.form import FormIndexer


@pytest_asyncio.fixture(autouse=True)
async def cleanup_forms(db_session: AsyncSession):
    """Clean up test forms after each test."""
    yield
    await db_session.execute(
        delete(Form).where(Form.created_by == "file_sync")
    )
    await db_session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
class TestFormIndexer:
    async def test_index_form_with_workflow_alias(self, db_session: AsyncSession):
        """FormIndexer should accept 'workflow' as alias for 'workflow_id'."""
        wf_id = uuid4()
        form_yaml = f"""name: Test Form Alias
workflow: {wf_id}
"""
        indexer = FormIndexer(db_session)
        await indexer.index_form("forms/test.form.yaml", form_yaml.encode())
        await db_session.flush()

        form = (await db_session.execute(
            select(Form).where(Form.name == "Test Form Alias")
        )).scalar_one()
        assert str(form.workflow_id) == str(wf_id)

    async def test_index_form_with_flat_fields(self, db_session: AsyncSession):
        """FormIndexer should accept flat 'fields' array (not nested in form_schema)."""
        form_yaml = """name: Flat Fields Form
fields:
- name: email
  type: text
  label: Email
  required: true
- name: count
  type: number
  label: Count
  default: 5
"""
        indexer = FormIndexer(db_session)
        await indexer.index_form("forms/test.form.yaml", form_yaml.encode())
        await db_session.flush()

        form = (await db_session.execute(
            select(Form).where(Form.name == "Flat Fields Form")
        )).scalar_one()
        fields = (await db_session.execute(
            select(FormField).where(FormField.form_id == form.id).order_by(FormField.position)
        )).scalars().all()
        assert len(fields) == 2
        assert fields[0].name == "email"
        assert fields[1].default_value == 5

    async def test_index_form_with_form_schema_fields(self, db_session: AsyncSession):
        """FormIndexer should still work with canonical form_schema.fields format."""
        form_yaml = """name: Schema Fields Form
form_schema:
  fields:
  - name: email
    type: text
    label: Email
    required: true
"""
        indexer = FormIndexer(db_session)
        await indexer.index_form("forms/test2.form.yaml", form_yaml.encode())
        await db_session.flush()

        form = (await db_session.execute(
            select(Form).where(Form.name == "Schema Fields Form")
        )).scalar_one()
        fields = (await db_session.execute(
            select(FormField).where(FormField.form_id == form.id)
        )).scalars().all()
        assert len(fields) == 1
        assert fields[0].name == "email"
