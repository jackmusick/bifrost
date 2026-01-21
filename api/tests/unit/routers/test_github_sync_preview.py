"""Test sync preview endpoint enriches conflicts with metadata."""
from src.services.github_sync_entity_metadata import extract_entity_metadata


def test_extract_entity_metadata_for_form():
    """Form files should extract name from JSON content."""
    content = b'{"name": "Contact Form", "fields": []}'
    metadata = extract_entity_metadata("forms/contact.form.json", content)

    assert metadata.entity_type == "form"
    assert metadata.display_name == "Contact Form"
    assert metadata.parent_slug is None


def test_extract_entity_metadata_for_agent():
    """Agent files should extract name from JSON content."""
    content = b'{"name": "Support Agent", "model": "gpt-4"}'
    metadata = extract_entity_metadata("agents/support.agent.json", content)

    assert metadata.entity_type == "agent"
    assert metadata.display_name == "Support Agent"
    assert metadata.parent_slug is None


def test_extract_entity_metadata_for_app():
    """App metadata should extract name and include parent_slug."""
    content = b'{"name": "Dashboard App", "version": "1.0"}'
    metadata = extract_entity_metadata("apps/dashboard/app.json", content)

    assert metadata.entity_type == "app"
    assert metadata.display_name == "Dashboard App"
    assert metadata.parent_slug == "dashboard"


def test_extract_entity_metadata_for_app_file():
    """App files should have parent_slug and relative path as display_name."""
    metadata = extract_entity_metadata("apps/dashboard/src/index.tsx", None)

    assert metadata.entity_type == "app_file"
    assert metadata.display_name == "src/index.tsx"
    assert metadata.parent_slug == "dashboard"
