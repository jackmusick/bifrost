"""Tests for manifest generator — serializes DB state to manifest."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4


@pytest.fixture
def mock_db():
    return AsyncMock()


def _mock_workflow(name="test_wf", org_id=None):
    wf = MagicMock()
    wf.id = uuid4()
    wf.name = name
    wf.function_name = name
    wf.path = f"workflows/{name}.py"
    wf.type = "workflow"
    wf.organization_id = org_id
    wf.access_level = "role_based"
    wf.endpoint_enabled = False
    wf.timeout_seconds = 1800
    wf.public_endpoint = False
    wf.category = "General"
    wf.tags = []
    wf.is_active = True
    wf.workflow_roles = []
    return wf


def _mock_form(name="test_form", org_id=None, workflow_id=None):
    form = MagicMock()
    form.id = uuid4()
    form.name = name
    form.organization_id = org_id
    form.workflow_id = str(workflow_id) if workflow_id else None
    form.is_active = True
    form.form_roles = []
    return form


@pytest.mark.asyncio
async def test_generate_manifest_with_workflow(mock_db):
    """Should include active workflows in manifest."""
    from src.services.manifest_generator import generate_manifest

    wf = _mock_workflow()

    # Mock: workflows query returns our workflow
    wf_result = MagicMock()
    wf_result.scalars.return_value.all.return_value = [wf]

    # Mock: other queries return empty
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []

    mock_db.execute = AsyncMock(side_effect=[
        wf_result,     # workflows
        empty_result,  # forms
        empty_result,  # agents
        empty_result,  # apps
        empty_result,  # organizations
        empty_result,  # roles
        empty_result,  # workflow_roles
        empty_result,  # form_roles
    ])

    manifest = await generate_manifest(mock_db)

    assert "test_wf" in manifest.workflows
    assert manifest.workflows["test_wf"].id == str(wf.id)
    assert manifest.workflows["test_wf"].path == "workflows/test_wf.py"


@pytest.mark.asyncio
async def test_generate_manifest_empty_db(mock_db):
    """Empty DB should produce empty manifest."""
    from src.services.manifest_generator import generate_manifest

    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=empty_result)

    manifest = await generate_manifest(mock_db)

    assert len(manifest.workflows) == 0
    assert len(manifest.forms) == 0
    assert len(manifest.agents) == 0
    assert len(manifest.apps) == 0


@pytest.mark.asyncio
async def test_generate_manifest_with_roles(mock_db):
    """Should include role assignments for workflows and forms."""
    from src.services.manifest_generator import generate_manifest

    role_id_1 = uuid4()
    role_id_2 = uuid4()

    # Workflow with roles
    wf = _mock_workflow(name="admin_wf")

    # Form with roles
    form = _mock_form(name="admin_form")

    # WorkflowRole entries
    wf_role_1 = MagicMock()
    wf_role_1.workflow_id = wf.id
    wf_role_1.role_id = role_id_1
    wf_role_2 = MagicMock()
    wf_role_2.workflow_id = wf.id
    wf_role_2.role_id = role_id_2

    # FormRole entries
    form_role_1 = MagicMock()
    form_role_1.form_id = form.id
    form_role_1.role_id = role_id_1

    wf_result = MagicMock()
    wf_result.scalars.return_value.all.return_value = [wf]

    form_result = MagicMock()
    form_result.scalars.return_value.all.return_value = [form]

    wf_roles_result = MagicMock()
    wf_roles_result.scalars.return_value.all.return_value = [wf_role_1, wf_role_2]

    form_roles_result = MagicMock()
    form_roles_result.scalars.return_value.all.return_value = [form_role_1]

    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []

    mock_db.execute = AsyncMock(side_effect=[
        wf_result,          # workflows
        form_result,        # forms
        empty_result,       # agents
        empty_result,       # apps
        empty_result,       # organizations
        empty_result,       # roles
        wf_roles_result,    # workflow_roles
        form_roles_result,  # form_roles
    ])

    manifest = await generate_manifest(mock_db)

    # Verify workflow roles
    assert "admin_wf" in manifest.workflows
    assert len(manifest.workflows["admin_wf"].roles) == 2
    assert str(role_id_1) in manifest.workflows["admin_wf"].roles
    assert str(role_id_2) in manifest.workflows["admin_wf"].roles

    # Verify form roles
    assert "admin_form" in manifest.forms
    assert len(manifest.forms["admin_form"].roles) == 1
    assert str(role_id_1) in manifest.forms["admin_form"].roles


@pytest.mark.asyncio
async def test_generate_manifest_with_organizations(mock_db):
    """Should include organization bindings for entities."""
    from src.services.manifest_generator import generate_manifest

    org_id = uuid4()

    # Workflow bound to org
    wf = _mock_workflow(name="org_wf", org_id=org_id)

    # Form bound to org
    form = _mock_form(name="org_form", org_id=org_id)

    wf_result = MagicMock()
    wf_result.scalars.return_value.all.return_value = [wf]

    form_result = MagicMock()
    form_result.scalars.return_value.all.return_value = [form]

    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []

    mock_db.execute = AsyncMock(side_effect=[
        wf_result,     # workflows
        form_result,   # forms
        empty_result,  # agents
        empty_result,  # apps
        empty_result,  # organizations
        empty_result,  # roles
        empty_result,  # workflow_roles
        empty_result,  # form_roles
    ])

    manifest = await generate_manifest(mock_db)

    # Verify org bindings
    assert manifest.workflows["org_wf"].organization_id == str(org_id)
    assert manifest.forms["org_form"].organization_id == str(org_id)
