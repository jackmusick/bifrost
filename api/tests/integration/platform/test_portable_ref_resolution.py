"""
Integration tests for portable workflow reference resolution.

Tests the complete indexing flow:
1. Create workflow in database
2. Create form/agent JSON with portable refs
3. Run indexer
4. Verify UUIDs are properly resolved in database

Additional round-trip tests:
5. Export entity to JSON (serialize)
6. Import JSON back (deserialize)
7. Verify SHA matches original - proving deterministic serialization

These tests specifically verify the Pydantic field_validator approach
for resolving data_provider_id and other nested workflow refs.
"""

import json
import logging
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import Form, FormField as FormFieldORM, Workflow, WorkspaceFile
from src.models.enums import GitStatus
from src.models.orm import Agent, AgentTool
from src.services.file_storage.indexers.form import FormIndexer, _serialize_form_to_json
from src.services.file_storage.indexers.agent import AgentIndexer, _serialize_agent_to_json
from src.services.file_storage.file_ops import compute_git_blob_sha
from src.services.file_storage.ref_translation import build_workflow_ref_map

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture
async def clean_test_data(db_session: AsyncSession):
    """
    Clean up test data before and after tests.
    """
    async def cleanup():
        # Delete form fields first (FK to forms)
        forms_to_delete = await db_session.execute(
            select(Form.id).where(
                Form.name.like("Test Portable Ref%") |
                Form.name.like("Test Data Provider%")
            )
        )
        form_ids = [r[0] for r in forms_to_delete.fetchall()]
        if form_ids:
            await db_session.execute(
                delete(FormFieldORM).where(FormFieldORM.form_id.in_(form_ids))
            )

        # Delete forms
        await db_session.execute(
            delete(Form).where(
                Form.name.like("Test Portable Ref%") |
                Form.name.like("Test Data Provider%")
            )
        )

        # Delete agent tools (FK to agents)
        agents_to_delete = await db_session.execute(
            select(Agent.id).where(
                Agent.name.like("Test Portable Ref%")
            )
        )
        agent_ids = [r[0] for r in agents_to_delete.fetchall()]
        if agent_ids:
            await db_session.execute(
                delete(AgentTool).where(AgentTool.agent_id.in_(agent_ids))
            )

        # Delete agents
        await db_session.execute(
            delete(Agent).where(
                Agent.name.like("Test Portable Ref%")
            )
        )

        # Delete test workflows
        await db_session.execute(
            delete(Workflow).where(
                Workflow.path.like("workflows/test_portable_ref_%") |
                Workflow.path.like("workflows/test_data_provider_%")
            )
        )

        # Delete test workspace files
        await db_session.execute(
            delete(WorkspaceFile).where(
                WorkspaceFile.path.like("forms/test_portable_ref_%") |
                WorkspaceFile.path.like("agents/test_portable_ref_%")
            )
        )

        await db_session.commit()

    # Cleanup before test
    await cleanup()

    yield

    # Cleanup after test
    await cleanup()


@pytest_asyncio.fixture
async def test_workflow(db_session: AsyncSession, clean_test_data):  # noqa: ARG001
    """
    Create a workflow for testing portable ref resolution.
    """
    workflow_id = uuid4()
    workflow_path = f"workflows/test_portable_ref_{workflow_id.hex[:8]}.py"
    workflow_function = f"test_portable_ref_{workflow_id.hex[:8]}"

    workflow = Workflow(
        id=workflow_id,
        name=workflow_function,
        function_name=workflow_function,
        path=workflow_path,
        description="Test workflow for portable ref resolution",
        type="data_provider",  # data_provider type for data_provider_id tests
        is_active=True,
        category="test",
    )
    db_session.add(workflow)
    await db_session.commit()

    portable_ref = f"{workflow_path}::{workflow_function}"
    logger.info(f"Created test workflow: {workflow_id} ({portable_ref})")

    yield {
        "id": workflow_id,
        "path": workflow_path,
        "function_name": workflow_function,
        "portable_ref": portable_ref,
    }


@pytest_asyncio.fixture
async def workspace_file_for_form(db_session: AsyncSession, clean_test_data):  # noqa: ARG001
    """
    Create a workspace file entry for a form.
    This is needed because the indexer updates the WorkspaceFile with entity info.
    """
    file_id = uuid4()
    form_id = uuid4()
    path = f"forms/test_portable_ref_{form_id}.form.json"

    workspace_file = WorkspaceFile(
        id=file_id,
        path=path,
        content_hash=f"test_sha_{file_id.hex[:8]}" + "0" * 40,  # 64 char hash
        size_bytes=1000,
        git_status=GitStatus.SYNCED,
    )
    db_session.add(workspace_file)
    await db_session.commit()

    yield {
        "id": file_id,
        "path": path,
        "form_id": form_id,
    }


@pytest_asyncio.fixture
async def workspace_file_for_agent(db_session: AsyncSession, clean_test_data):  # noqa: ARG001
    """
    Create a workspace file entry for an agent.
    """
    file_id = uuid4()
    agent_id = uuid4()
    path = f"agents/test_portable_ref_{agent_id}.agent.json"

    workspace_file = WorkspaceFile(
        id=file_id,
        path=path,
        content_hash=f"test_sha_{file_id.hex[:8]}" + "0" * 40,  # 64 char hash
        size_bytes=500,
        git_status=GitStatus.SYNCED,
    )
    db_session.add(workspace_file)
    await db_session.commit()

    yield {
        "id": file_id,
        "path": path,
        "agent_id": agent_id,
    }


@pytest.mark.integration
class TestFormPortableRefResolution:
    """Test form indexer resolves portable refs to UUIDs."""

    @pytest.mark.asyncio
    async def test_form_data_provider_id_resolution(
        self,
        db_session: AsyncSession,
        test_workflow,
        workspace_file_for_form,
    ):
        """
        Test that data_provider_id portable refs in form fields are resolved.

        This is the main bug case: form_schema.fields.*.data_provider_id
        contains a portable ref that needs to be translated to a UUID.
        """
        portable_ref = test_workflow["portable_ref"]
        workflow_id = test_workflow["id"]
        form_path = workspace_file_for_form["path"]
        form_id = workspace_file_for_form["form_id"]

        # Create form JSON with portable refs
        form_json = {
            "id": str(form_id),
            "name": "Test Portable Ref Form",
            "description": "Form for testing data_provider_id resolution",
            "workflow_id": portable_ref,
            "launch_workflow_id": portable_ref,
            "form_schema": {
                "fields": [
                    {
                        "name": "text_field",
                        "label": "Text Field",
                        "type": "text",
                        "required": True,
                    },
                    {
                        "name": "dropdown_field",
                        "label": "Dropdown",
                        "type": "select",
                        "data_provider_id": portable_ref,  # THIS IS THE BUG CASE
                    },
                    {
                        "name": "another_dropdown",
                        "label": "Another Dropdown",
                        "type": "select",
                        "data_provider_id": portable_ref,  # Multiple fields
                    },
                ]
            },
            "_export": {
                "workflow_refs": [
                    "workflow_id",
                    "launch_workflow_id",
                    "form_schema.fields.*.data_provider_id",  # Wildcard pattern
                ],
                "version": "1.0",
            },
        }

        content = json.dumps(form_json).encode("utf-8")

        # Run form indexer
        indexer = FormIndexer(db_session)
        await indexer.index_form(form_path, content)
        await db_session.commit()

        # Verify form was created
        form_result = await db_session.execute(
            select(Form).where(Form.id == form_id)
        )
        form = form_result.scalar_one()

        # Check workflow_id resolved
        assert str(form.workflow_id) == str(workflow_id), (
            f"workflow_id not resolved: expected {workflow_id}, got {form.workflow_id}"
        )

        # Check launch_workflow_id resolved
        assert str(form.launch_workflow_id) == str(workflow_id), (
            f"launch_workflow_id not resolved: expected {workflow_id}, got {form.launch_workflow_id}"
        )

        # Check ALL data_provider_ids resolved
        fields_result = await db_session.execute(
            select(FormFieldORM).where(FormFieldORM.form_id == form_id)
        )
        fields = fields_result.scalars().all()

        for field in fields:
            if field.name in ["dropdown_field", "another_dropdown"]:
                assert field.data_provider_id is not None, (
                    f"Field {field.name} data_provider_id is None"
                )
                assert str(field.data_provider_id) == str(workflow_id), (
                    f"Field {field.name} data_provider_id not resolved: "
                    f"expected {workflow_id}, got {field.data_provider_id}"
                )

        logger.info("Form data_provider_id resolution test passed!")

    @pytest.mark.asyncio
    async def test_form_without_export_metadata(
        self,
        db_session: AsyncSession,
        test_workflow,
        workspace_file_for_form,
    ):
        """
        Test form indexing works when there's no _export metadata.

        This verifies the indexer handles plain UUID strings correctly.
        """
        workflow_id = test_workflow["id"]
        form_path = workspace_file_for_form["path"]
        form_id = workspace_file_for_form["form_id"]

        # Create form JSON with UUIDs (no portable refs)
        form_json = {
            "id": str(form_id),
            "name": "Test Portable Ref Form No Export",
            "description": "Form without export metadata",
            "workflow_id": str(workflow_id),
            "form_schema": {
                "fields": [
                    {
                        "name": "text_field",
                        "label": "Text Field",
                        "type": "text",
                    },
                    {
                        "name": "dropdown_field",
                        "label": "Dropdown",
                        "type": "select",
                        "data_provider_id": str(workflow_id),
                    },
                ]
            },
            # No _export metadata
        }

        content = json.dumps(form_json).encode("utf-8")

        # Run form indexer
        indexer = FormIndexer(db_session)
        await indexer.index_form(form_path, content)
        await db_session.commit()

        # Verify form was created with correct UUIDs
        form_result = await db_session.execute(
            select(Form).where(Form.id == form_id)
        )
        form = form_result.scalar_one()
        assert str(form.workflow_id) == str(workflow_id)

        # Verify field data_provider_id
        fields_result = await db_session.execute(
            select(FormFieldORM).where(FormFieldORM.form_id == form_id)
        )
        fields = fields_result.scalars().all()

        dropdown_field = next((f for f in fields if f.name == "dropdown_field"), None)
        assert dropdown_field is not None
        assert str(dropdown_field.data_provider_id) == str(workflow_id)

        logger.info("Form without export metadata test passed!")

    @pytest.mark.asyncio
    async def test_form_with_unresolvable_ref(
        self,
        db_session: AsyncSession,
        workspace_file_for_form,
    ):
        """
        Test that unresolvable portable refs fail gracefully.

        When a workflow doesn't exist, the ref should remain as-is
        and validation should fail with a clear error (or field should be skipped).
        """
        form_path = workspace_file_for_form["path"]
        form_id = workspace_file_for_form["form_id"]
        non_existent_ref = "workflows/does_not_exist.py::missing_function"

        # Create form JSON with non-existent workflow ref
        form_json = {
            "id": str(form_id),
            "name": "Test Portable Ref Form Unresolvable",
            "description": "Form with unresolvable ref",
            "workflow_id": non_existent_ref,
            "form_schema": {
                "fields": [
                    {
                        "name": "text_field",
                        "label": "Text Field",
                        "type": "text",
                    },
                    {
                        "name": "dropdown_field",
                        "label": "Dropdown",
                        "type": "select",
                        "data_provider_id": non_existent_ref,
                    },
                ]
            },
            "_export": {
                "workflow_refs": [
                    "workflow_id",
                    "form_schema.fields.*.data_provider_id",
                ],
            },
        }

        content = json.dumps(form_json).encode("utf-8")

        # Run form indexer - should not crash
        indexer = FormIndexer(db_session)
        await indexer.index_form(form_path, content)
        await db_session.commit()

        # Form should be created (graceful degradation)
        form_result = await db_session.execute(
            select(Form).where(Form.id == form_id)
        )
        form = form_result.scalar_one_or_none()
        assert form is not None, "Form should be created even with unresolvable refs"

        # workflow_id should remain as string (not a UUID), which will be None
        # since it can't be cast to UUID in the database
        # (The exact behavior depends on the database schema - it may be NULL or the string)

        logger.info("Form with unresolvable ref test passed!")


@pytest.mark.integration
class TestAgentPortableRefResolution:
    """Test agent indexer resolves portable refs to UUIDs."""

    @pytest.mark.asyncio
    async def test_agent_tool_ids_resolution(
        self,
        db_session: AsyncSession,
        test_workflow,
        workspace_file_for_agent,
    ):
        """
        Test that tool_ids portable refs are resolved.
        """
        portable_ref = test_workflow["portable_ref"]
        workflow_id = test_workflow["id"]
        agent_path = workspace_file_for_agent["path"]
        agent_id = workspace_file_for_agent["agent_id"]

        # Create agent JSON with portable refs
        agent_json = {
            "id": str(agent_id),
            "name": "Test Portable Ref Agent",
            "description": "Agent for testing tool_ids resolution",
            "system_prompt": "You are a test agent.",
            "channels": ["chat"],
            "tool_ids": [portable_ref, portable_ref],  # Multiple tools
            "_export": {
                "workflow_refs": ["tool_ids.*"],
                "version": "1.0",
            },
        }

        content = json.dumps(agent_json).encode("utf-8")

        # Run agent indexer
        indexer = AgentIndexer(db_session)
        await indexer.index_agent(agent_path, content)
        await db_session.commit()

        # Verify agent was created
        agent_result = await db_session.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        agent = agent_result.scalar_one()
        assert agent is not None

        # Verify tool associations were created with resolved UUIDs
        tools_result = await db_session.execute(
            select(AgentTool).where(AgentTool.agent_id == agent_id)
        )
        tools = tools_result.scalars().all()

        # Should have at least one tool (duplicates may be deduplicated)
        assert len(tools) >= 1, "Agent should have tool associations"

        for tool in tools:
            assert str(tool.workflow_id) == str(workflow_id), (
                f"Tool workflow_id not resolved: expected {workflow_id}, got {tool.workflow_id}"
            )

        logger.info("Agent tool_ids resolution test passed!")

    @pytest.mark.asyncio
    async def test_agent_with_mixed_refs(
        self,
        db_session: AsyncSession,
        test_workflow,
        workspace_file_for_agent,
    ):
        """
        Test agent with mix of UUIDs and portable refs.
        """
        portable_ref = test_workflow["portable_ref"]
        workflow_id = test_workflow["id"]
        agent_path = workspace_file_for_agent["path"]
        agent_id = workspace_file_for_agent["agent_id"]

        # Create agent JSON with mix of UUID and portable ref
        agent_json = {
            "id": str(agent_id),
            "name": "Test Portable Ref Agent Mixed",
            "description": "Agent with mixed refs",
            "system_prompt": "You are a test agent.",
            "channels": ["chat"],
            "tool_ids": [str(workflow_id), portable_ref],  # One UUID, one portable ref
            "_export": {
                "workflow_refs": ["tool_ids.*"],
            },
        }

        content = json.dumps(agent_json).encode("utf-8")

        # Run agent indexer
        indexer = AgentIndexer(db_session)
        await indexer.index_agent(agent_path, content)
        await db_session.commit()

        # Verify tool associations
        tools_result = await db_session.execute(
            select(AgentTool).where(AgentTool.agent_id == agent_id)
        )
        tools = tools_result.scalars().all()

        # All tools should resolve to the same workflow
        for tool in tools:
            assert str(tool.workflow_id) == str(workflow_id)

        logger.info("Agent with mixed refs test passed!")


@pytest.mark.integration
class TestRoundTripSHAConsistency:
    """
    Test that round-trip serialization produces identical SHA.

    This is critical for GitHub sync - if we export a form/agent to GitHub
    and then re-import it, the SHA must match on re-export.

    Real-world flow:
    1. Create entity in database (like UI would)
    2. Export to JSON (this is what goes to GitHub)
    3. Import that JSON back (simulate sync from GitHub)
    4. Export again
    5. Compare SHA from step 2 and step 4 - must match!
    """

    @pytest.mark.asyncio
    async def test_form_round_trip_sha_match(
        self,
        db_session: AsyncSession,
        test_workflow,
    ):
        """
        Test form: create -> export -> import -> export produces identical SHA.

        This catches bugs where timestamps or other non-deterministic fields
        cause SHA differences on every sync cycle.
        """
        workflow_id = test_workflow["id"]

        # Step 1: Create a real form in the database (like the UI would)
        form_id = uuid4()
        form = Form(
            id=form_id,
            name="Test Round Trip Form",
            description="Form for testing SHA consistency",
            workflow_id=str(workflow_id),  # VARCHAR column
            launch_workflow_id=str(workflow_id),  # VARCHAR column
            is_active=True,
            created_by="test",
        )
        db_session.add(form)
        await db_session.flush()

        # Add fields
        field1 = FormFieldORM(
            id=uuid4(),
            form_id=form_id,
            name="text_field",
            label="Text Field",
            type="text",
            required=True,
            position=0,
        )
        field2 = FormFieldORM(
            id=uuid4(),
            form_id=form_id,
            name="dropdown_field",
            label="Dropdown",
            type="select",
            required=False,
            data_provider_id=workflow_id,
            position=1,
        )
        db_session.add_all([field1, field2])
        await db_session.commit()

        # Step 2: Export to JSON (this is what would go to GitHub)
        form_result = await db_session.execute(
            select(Form)
            .options(selectinload(Form.fields))
            .where(Form.id == form_id)
        )
        form = form_result.scalar_one()

        workflow_map = await build_workflow_ref_map(db_session)
        exported_content_1 = _serialize_form_to_json(form, workflow_map)
        sha_1 = compute_git_blob_sha(exported_content_1)
        logger.info(f"First export SHA: {sha_1}")
        logger.info(f"First export content:\n{exported_content_1.decode()}")

        # Step 3: Import that JSON back (simulate pulling from GitHub)
        # First delete the form to simulate fresh import
        await db_session.execute(
            delete(FormFieldORM).where(FormFieldORM.form_id == form_id)
        )
        await db_session.execute(
            delete(Form).where(Form.id == form_id)
        )
        await db_session.commit()

        indexer = FormIndexer(db_session)
        form_path = f"forms/{form_id}.form.json"
        await indexer.index_form(form_path, exported_content_1)
        await db_session.commit()

        # Step 4: Export again
        form_result = await db_session.execute(
            select(Form)
            .options(selectinload(Form.fields))
            .where(Form.id == form_id)
        )
        form = form_result.scalar_one()

        exported_content_2 = _serialize_form_to_json(form, workflow_map)
        sha_2 = compute_git_blob_sha(exported_content_2)
        logger.info(f"Second export SHA: {sha_2}")

        # Step 5: SHAs must match!
        if sha_1 != sha_2:
            logger.error(f"First export:\n{exported_content_1.decode()}")
            logger.error(f"Second export:\n{exported_content_2.decode()}")

        assert sha_1 == sha_2, (
            f"Round-trip SHA mismatch! First: {sha_1}, Second: {sha_2}. "
            "This will cause spurious conflicts in GitHub sync."
        )

        logger.info("Form round-trip SHA consistency test passed!")

    @pytest.mark.asyncio
    async def test_agent_round_trip_sha_match(
        self,
        db_session: AsyncSession,
        test_workflow,
    ):
        """
        Test agent: create -> export -> import -> export produces identical SHA.
        """
        workflow_id = test_workflow["id"]

        # Step 1: Create a real agent in the database
        agent_id = uuid4()
        agent = Agent(
            id=agent_id,
            name="Test Round Trip Agent",
            description="Agent for testing SHA consistency",
            system_prompt="You are a test agent.",
            channels=["chat"],
            is_active=True,
            is_coding_mode=False,
            created_by="test",
        )
        db_session.add(agent)
        await db_session.flush()

        # Add tool association
        agent_tool = AgentTool(
            agent_id=agent_id,
            workflow_id=workflow_id,
        )
        db_session.add(agent_tool)
        await db_session.commit()

        # Step 2: Export to JSON
        agent_result = await db_session.execute(
            select(Agent)
            .options(
                selectinload(Agent.tools),
                selectinload(Agent.delegated_agents),
                selectinload(Agent.roles),
            )
            .where(Agent.id == agent_id)
        )
        agent = agent_result.scalar_one()

        workflow_map = await build_workflow_ref_map(db_session)
        exported_content_1 = _serialize_agent_to_json(agent, workflow_map)
        sha_1 = compute_git_blob_sha(exported_content_1)
        logger.info(f"First export SHA: {sha_1}")
        logger.info(f"First export content:\n{exported_content_1.decode()}")

        # Step 3: Import that JSON back
        # Delete agent to simulate fresh import
        await db_session.execute(
            delete(AgentTool).where(AgentTool.agent_id == agent_id)
        )
        await db_session.execute(
            delete(Agent).where(Agent.id == agent_id)
        )
        await db_session.commit()

        indexer = AgentIndexer(db_session)
        agent_path = f"agents/{agent_id}.agent.json"
        await indexer.index_agent(agent_path, exported_content_1)
        await db_session.commit()

        # Step 4: Export again
        agent_result = await db_session.execute(
            select(Agent)
            .options(
                selectinload(Agent.tools),
                selectinload(Agent.delegated_agents),
                selectinload(Agent.roles),
            )
            .where(Agent.id == agent_id)
        )
        agent = agent_result.scalar_one()

        exported_content_2 = _serialize_agent_to_json(agent, workflow_map)
        sha_2 = compute_git_blob_sha(exported_content_2)
        logger.info(f"Second export SHA: {sha_2}")

        # Step 5: SHAs must match!
        if sha_1 != sha_2:
            logger.error(f"First export:\n{exported_content_1.decode()}")
            logger.error(f"Second export:\n{exported_content_2.decode()}")

        assert sha_1 == sha_2, (
            f"Round-trip SHA mismatch! First: {sha_1}, Second: {sha_2}. "
            "This will cause spurious conflicts in GitHub sync."
        )

        logger.info("Agent round-trip SHA consistency test passed!")

    @pytest.mark.asyncio
    async def test_form_export_stability(
        self,
        db_session: AsyncSession,
        test_workflow,
    ):
        """
        Test that exporting the same form multiple times produces identical SHA.

        This verifies serialization is deterministic (no random ordering, etc).
        """
        workflow_id = test_workflow["id"]

        # Create a form
        form_id = uuid4()
        form = Form(
            id=form_id,
            name="Test Export Stability Form",
            description="Testing export stability",
            workflow_id=str(workflow_id),  # VARCHAR column
            is_active=True,
            created_by="test",
        )
        db_session.add(form)
        await db_session.flush()

        field = FormFieldORM(
            id=uuid4(),
            form_id=form_id,
            name="field1",
            label="Field 1",
            type="text",
            required=False,
            position=0,
        )
        db_session.add(field)
        await db_session.commit()

        workflow_map = await build_workflow_ref_map(db_session)

        # Export multiple times
        shas = []
        for i in range(3):
            form_result = await db_session.execute(
                select(Form)
                .options(selectinload(Form.fields))
                .where(Form.id == form_id)
            )
            form = form_result.scalar_one()

            exported_content = _serialize_form_to_json(form, workflow_map)
            sha = compute_git_blob_sha(exported_content)
            shas.append(sha)
            logger.info(f"Export {i + 1} SHA: {sha}")

        # All SHAs must be identical
        assert all(sha == shas[0] for sha in shas), (
            f"Export SHA not stable across multiple exports: {shas}"
        )

        logger.info("Form export stability test passed!")
