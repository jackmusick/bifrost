from pathlib import Path

import yaml

from bifrost.integration_definition import (
    SourceIntegrationDefinition,
    discover_integration_definitions,
    load_integration_definition,
)

DNSFILTER_DEFINITION = {
    "id": "82252311-d1d6-4d69-b26f-b42989e60d03",
    "name": "DNSFilter",
    "list_entities_data_provider_id": "41d3fef1-f134-4ca9-a61a-4c9417151647",
    "config_schema": [
        {
            "key": "api_key",
            "type": "secret",
            "required": True,
            "description": "DNSFilter API key",
            "position": 0,
        }
    ],
}


def _write_integration_definition(repo_root: Path, slug: str, data: dict) -> Path:
    definition_path = repo_root / "integrations" / slug / "integration.yaml"
    definition_path.parent.mkdir(parents=True, exist_ok=True)
    definition_path.write_text(yaml.safe_dump(data))
    return definition_path


def test_load_integration_definition_from_yaml(tmp_path: Path) -> None:
    definition_path = _write_integration_definition(tmp_path, "dnsfilter", DNSFILTER_DEFINITION)
    definition = load_integration_definition(definition_path)

    assert isinstance(definition, SourceIntegrationDefinition)
    assert definition.id == "82252311-d1d6-4d69-b26f-b42989e60d03"
    assert definition.name == "DNSFilter"
    assert definition.list_entities_data_provider_id == "41d3fef1-f134-4ca9-a61a-4c9417151647"
    assert len(definition.config_schema) == 1
    assert definition.config_schema[0].key == "api_key"
    assert definition.oauth_provider is None


def test_integration_definition_bridges_to_manifest_shape(tmp_path: Path) -> None:
    definition_path = _write_integration_definition(tmp_path, "dnsfilter", DNSFILTER_DEFINITION)
    definition = load_integration_definition(definition_path)

    manifest_dict = definition.to_manifest_dict()

    assert manifest_dict["id"] == definition.id
    assert manifest_dict["name"] == definition.name
    assert manifest_dict["mappings"] == []
    assert manifest_dict["config_schema"][0]["key"] == "api_key"


def test_discover_integration_definitions(tmp_path: Path) -> None:
    _write_integration_definition(tmp_path, "dnsfilter", DNSFILTER_DEFINITION)
    _write_integration_definition(
        tmp_path,
        "ninjaone",
        {
            "id": "f6e3dcab-2906-4ef6-b7f4-3fb3f3b03f34",
            "name": "NinjaOne",
            "config_schema": [],
        },
    )

    definitions = discover_integration_definitions(tmp_path)

    assert "dnsfilter" in definitions
    assert definitions["dnsfilter"].name == "DNSFilter"
    assert "ninjaone" in definitions
