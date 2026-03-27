from pathlib import Path

from bifrost.integration_definition import (
    SourceIntegrationDefinition,
    discover_integration_definitions,
    load_integration_definition,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


def test_load_dnsfilter_integration_definition() -> None:
    definition = load_integration_definition(
        REPO_ROOT / "integrations" / "dnsfilter" / "integration.yaml"
    )

    assert isinstance(definition, SourceIntegrationDefinition)
    assert definition.id == "82252311-d1d6-4d69-b26f-b42989e60d03"
    assert definition.name == "DNSFilter"
    assert definition.list_entities_data_provider_id == "41d3fef1-f134-4ca9-a61a-4c9417151647"
    assert len(definition.config_schema) == 1
    assert definition.config_schema[0].key == "api_key"
    assert definition.oauth_provider is None


def test_dnsfilter_definition_bridges_to_manifest_shape() -> None:
    definition = load_integration_definition(
        REPO_ROOT / "integrations" / "dnsfilter" / "integration.yaml"
    )

    manifest_dict = definition.to_manifest_dict()

    assert manifest_dict["id"] == definition.id
    assert manifest_dict["name"] == definition.name
    assert manifest_dict["mappings"] == []
    assert manifest_dict["config_schema"][0]["key"] == "api_key"


def test_discover_integration_definitions() -> None:
    definitions = discover_integration_definitions(REPO_ROOT)

    assert "dnsfilter" in definitions
    assert definitions["dnsfilter"].name == "DNSFilter"
