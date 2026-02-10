"""Tests for entity serializers — DB entities to YAML files."""
from unittest.mock import MagicMock
from uuid import uuid4

import yaml


def _mock_form_with_fields():
    form = MagicMock()
    form.id = uuid4()
    form.name = "Test Form"
    form.description = "A test form"
    form.workflow_id = str(uuid4())
    form.launch_workflow_id = None

    field1 = MagicMock()
    field1.name = "email"
    field1.type = "text"
    field1.label = "Email Address"
    field1.required = True
    field1.default_value = None
    field1.options = None
    field1.position = 0

    field2 = MagicMock()
    field2.name = "department"
    field2.type = "select"
    field2.label = "Department"
    field2.required = False
    field2.default_value = "Engineering"
    field2.options = ["Engineering", "Sales", "Support"]
    field2.position = 1

    form.fields = [field1, field2]
    return form


def _mock_agent():
    agent = MagicMock()
    agent.id = uuid4()
    agent.name = "Test Agent"
    agent.description = "A test agent"
    agent.system_prompt = "You are a helpful agent."
    agent.llm_model = "claude-sonnet-4-5-20250929"
    agent.llm_temperature = 0.7
    agent.llm_max_tokens = 4096

    tool1 = MagicMock()
    tool1.id = uuid4()
    agent.tools = [tool1]
    return agent


def test_serialize_form():
    """Serialize a form to YAML."""
    from src.services.entity_serializers import serialize_form_to_yaml

    form = _mock_form_with_fields()
    yaml_str = serialize_form_to_yaml(form)
    data = yaml.safe_load(yaml_str)

    assert data["name"] == "Test Form"
    assert data["description"] == "A test form"
    assert data["workflow"] == str(form.workflow_id)
    assert len(data["fields"]) == 2
    assert data["fields"][0]["name"] == "email"
    assert data["fields"][0]["type"] == "text"
    assert data["fields"][0]["required"] is True


def test_serialize_agent():
    """Serialize an agent to YAML."""
    from src.services.entity_serializers import serialize_agent_to_yaml

    agent = _mock_agent()
    yaml_str = serialize_agent_to_yaml(agent)
    data = yaml.safe_load(yaml_str)

    assert data["name"] == "Test Agent"
    assert data["system_prompt"] == "You are a helpful agent."
    assert len(data["tools"]) == 1
    assert data["tools"][0] == str(agent.tools[0].id)


def test_serialize_form_round_trip():
    """Serialized YAML should be valid and parseable."""
    from src.services.entity_serializers import serialize_form_to_yaml

    form = _mock_form_with_fields()
    yaml_str = serialize_form_to_yaml(form)
    data = yaml.safe_load(yaml_str)
    assert isinstance(data, dict)
