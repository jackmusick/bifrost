"""
Entity Serializers — convert DB entities to portable YAML files.

These YAML files contain no org, roles, or instance config.
Cross-references use UUIDs.
"""

from __future__ import annotations

import logging
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def serialize_form_to_yaml(form: Any) -> str:
    """Serialize a Form ORM object to portable YAML."""
    data: dict[str, Any] = {
        "name": form.name,
        "description": form.description,
        "workflow": str(form.workflow_id) if form.workflow_id else None,
        "launch_workflow": str(form.launch_workflow_id) if form.launch_workflow_id else None,
    }

    fields = []
    for field in sorted(form.fields, key=lambda f: f.position):
        field_data: dict[str, Any] = {
            "name": field.name,
            "type": field.type,
            "label": field.label,
        }
        if field.required:
            field_data["required"] = True
        if field.default_value is not None:
            field_data["default"] = field.default_value
        if field.options:
            field_data["options"] = field.options
        fields.append(field_data)

    data["fields"] = fields

    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


def serialize_agent_to_yaml(agent: Any) -> str:
    """Serialize an Agent ORM object to portable YAML."""
    data: dict[str, Any] = {
        "name": agent.name,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "llm_model": agent.llm_model,
    }

    if agent.llm_temperature is not None:
        data["llm_temperature"] = agent.llm_temperature
    if agent.llm_max_tokens is not None:
        data["llm_max_tokens"] = agent.llm_max_tokens

    # Tools are referenced by UUID
    if agent.tools:
        data["tools"] = [str(tool.id) for tool in agent.tools]
    else:
        data["tools"] = []

    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


def serialize_app_to_yaml(app: Any) -> str:
    """Serialize an Application ORM object to portable YAML."""
    data: dict[str, Any] = {
        "name": app.name,
        "description": getattr(app, "description", None),
    }

    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
