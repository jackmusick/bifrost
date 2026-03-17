"""Tests for RepoSyncWriter — dual-write forms/agents to S3 _repo/."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.repo_sync_writer import RepoSyncWriter


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.s3_configured = True
    settings.s3_bucket = "test-bucket"
    settings.s3_endpoint_url = "http://minio:9000"
    settings.s3_access_key = "test"
    settings.s3_secret_key = "test"
    settings.s3_region = "us-east-1"
    return settings


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def writer(mock_db, mock_settings):
    with patch("src.services.repo_sync_writer.get_settings", return_value=mock_settings):
        with patch("src.services.repo_sync_writer.RepoStorage"):
            w = RepoSyncWriter(mock_db)
            w._file_index = AsyncMock()
            w._file_index.write = AsyncMock(return_value="abc123")
            w._file_index.delete = AsyncMock()
            return w


class TestWriteForm:
    @pytest.mark.asyncio
    async def test_writes_yaml_to_s3(self, writer):
        from uuid import uuid4

        form_id = uuid4()
        form = MagicMock()
        form.id = form_id
        form.name = "Test Form"
        form.description = "A test form"
        form.workflow_id = None
        form.launch_workflow_id = None
        form.default_launch_params = None
        form.allowed_query_params = None
        form.form_schema = None
        form.access_level = None
        form.organization_id = None
        form.is_active = True
        form.created_at = None
        form.updated_at = None
        form.fields = []

        await writer.write_form(form)

        writer._file_index.write.assert_awaited_once()
        call_args = writer._file_index.write.call_args
        assert call_args[0][0] == f"forms/{form_id}.form.yaml"
        # Verify content is bytes (YAML encoded)
        assert isinstance(call_args[0][1], bytes)
        content = call_args[0][1].decode("utf-8")
        assert "Test Form" in content

    @pytest.mark.asyncio
    async def test_skips_when_s3_not_configured(self, writer, mock_settings):
        mock_settings.s3_configured = False
        form = MagicMock()
        form.id = "form-123"
        form.fields = []

        await writer.write_form(form)

        writer._file_index.write.assert_not_awaited()


class TestWriteAgent:
    @pytest.mark.asyncio
    async def test_writes_yaml_to_s3(self, writer):
        from uuid import uuid4

        agent_id = uuid4()
        agent = MagicMock()
        agent.id = agent_id
        agent.name = "Test Agent"
        agent.description = "A test agent"
        agent.system_prompt = "You are a test agent."
        agent.channels = ["chat"]
        agent.access_level = None
        agent.organization_id = None
        agent.is_active = True
        agent.is_system = False
        agent.created_by = None
        agent.owner_user_id = None
        agent.owner_email = None
        agent.created_at = None
        agent.updated_at = None
        agent.llm_model = "gpt-4"
        agent.llm_max_tokens = None
        agent.tools = []
        agent.delegations = []
        agent.roles = []
        agent.knowledge_sources = []
        agent.system_tools = []

        await writer.write_agent(agent)

        writer._file_index.write.assert_awaited_once()
        call_args = writer._file_index.write.call_args
        assert call_args[0][0] == f"agents/{agent_id}.agent.yaml"
        content = call_args[0][1].decode("utf-8")
        assert "Test Agent" in content
        assert "You are a test agent." in content

    @pytest.mark.asyncio
    async def test_skips_when_s3_not_configured(self, writer, mock_settings):
        mock_settings.s3_configured = False
        agent = MagicMock()
        agent.id = "agent-456"
        agent.tools = []

        await writer.write_agent(agent)

        writer._file_index.write.assert_not_awaited()


class TestDeleteEntityFile:
    @pytest.mark.asyncio
    async def test_deletes_from_s3_and_file_index(self, writer):
        await writer.delete_entity_file("forms/form-123.form.yaml")

        writer._file_index.delete.assert_awaited_once_with("forms/form-123.form.yaml")

    @pytest.mark.asyncio
    async def test_skips_when_s3_not_configured(self, writer, mock_settings):
        mock_settings.s3_configured = False

        await writer.delete_entity_file("forms/form-123.form.yaml")

        writer._file_index.delete.assert_not_awaited()


class TestRegenerateManifest:
    @pytest.mark.asyncio
    async def test_generates_and_writes_split_manifest_files(self, writer):
        from bifrost.manifest import Manifest, ManifestWorkflow

        mock_manifest = Manifest(
            workflows={
                "wf1": ManifestWorkflow(
                    id="11111111-1111-1111-1111-111111111111",
                    path="workflows/wf1.py",
                    function_name="wf1",
                )
            }
        )
        with patch(
            "src.services.repo_sync_writer.generate_manifest",
            new_callable=AsyncMock,
            return_value=mock_manifest,
        ):
            await writer.regenerate_manifest()

        # Should write split file(s), not single metadata.yaml
        write_calls = writer._file_index.write.call_args_list
        written_paths = [call[0][0] for call in write_calls]
        assert ".bifrost/workflows.yaml" in written_paths
        assert ".bifrost/metadata.yaml" not in written_paths

    @pytest.mark.asyncio
    async def test_empty_manifest_cleans_legacy(self, writer):
        from bifrost.manifest import Manifest

        mock_manifest = Manifest()
        with patch(
            "src.services.repo_sync_writer.generate_manifest",
            new_callable=AsyncMock,
            return_value=mock_manifest,
        ):
            await writer.regenerate_manifest()

        # No split files written for empty manifest
        writer._file_index.write.assert_not_awaited()
        # Should attempt to delete legacy file
        delete_calls = writer._file_index.delete.call_args_list
        deleted_paths = [call[0][0] for call in delete_calls]
        assert ".bifrost/metadata.yaml" in deleted_paths

    @pytest.mark.asyncio
    async def test_skips_when_s3_not_configured(self, writer, mock_settings):
        mock_settings.s3_configured = False

        await writer.regenerate_manifest()

        writer._file_index.write.assert_not_awaited()
