"""Tests for entity metadata extraction from sync files."""
from src.services.github_sync_entity_metadata import (
    extract_entity_metadata,
)


class TestExtractEntityMetadata:
    """Tests for extract_entity_metadata function."""

    def test_form_extracts_name(self):
        """Form JSON extracts name as display_name."""
        path = "forms/abc123.form.json"
        content = b'{"name": "Customer Intake", "id": "abc123"}'

        result = extract_entity_metadata(path, content)

        assert result.entity_type == "form"
        assert result.display_name == "Customer Intake"
        assert result.parent_slug is None

    def test_agent_extracts_name(self):
        """Agent JSON extracts name as display_name."""
        path = "agents/xyz789.agent.json"
        content = b'{"name": "Support Bot", "id": "xyz789"}'

        result = extract_entity_metadata(path, content)

        assert result.entity_type == "agent"
        assert result.display_name == "Support Bot"
        assert result.parent_slug is None

    def test_app_json_extracts_name(self):
        """App app.json extracts name as display_name."""
        path = "apps/dashboard/app.json"
        content = b'{"name": "Dashboard", "slug": "dashboard"}'

        result = extract_entity_metadata(path, content)

        assert result.entity_type == "app"
        assert result.display_name == "Dashboard"
        assert result.parent_slug == "dashboard"

    def test_app_file_extracts_parent_slug(self):
        """App code file extracts parent slug."""
        path = "apps/dashboard/pages/index.tsx"
        content = b'export default function Home() { return <div>Home</div> }'

        result = extract_entity_metadata(path, content)

        assert result.entity_type == "app_file"
        assert result.display_name == "pages/index.tsx"
        assert result.parent_slug == "dashboard"

    def test_workflow_uses_filename(self):
        """Workflow uses filename as display_name."""
        path = "workflows/process_payment.py"
        content = b'@workflow\ndef process_payment(): pass'

        result = extract_entity_metadata(path, content)

        assert result.entity_type == "workflow"
        assert result.display_name == "process_payment.py"
        assert result.parent_slug is None

    def test_unknown_file_returns_filename(self):
        """Unknown file type returns filename as display_name."""
        path = "random/file.txt"
        content = b'some content'

        result = extract_entity_metadata(path, content)

        assert result.entity_type is None
        assert result.display_name == "file.txt"
        assert result.parent_slug is None

    def test_invalid_json_uses_filename(self):
        """Invalid JSON falls back to filename."""
        path = "forms/broken.form.json"
        content = b'not valid json'

        result = extract_entity_metadata(path, content)

        assert result.entity_type == "form"
        assert result.display_name == "broken.form.json"
