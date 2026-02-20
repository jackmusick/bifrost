"""Tests for manifest parser."""
import pytest
from uuid import uuid4

import yaml


@pytest.fixture
def sample_manifest():
    """A valid manifest dict."""
    org_id = str(uuid4())
    role_id = str(uuid4())
    wf_id = str(uuid4())
    form_id = str(uuid4())
    return {
        "organizations": [{"id": org_id, "name": "TestOrg"}],
        "roles": [{"id": role_id, "name": "admin", "organization_id": org_id}],
        "workflows": {
            "my_workflow": {
                "id": wf_id,
                "path": "workflows/my_workflow.py",
                "function_name": "my_workflow",
                "type": "workflow",
                "organization_id": org_id,
                "roles": [role_id],
                "access_level": "role_based",
                "endpoint_enabled": False,
                "timeout_seconds": 1800,
            },
        },
        "forms": {
            "my_form": {
                "id": form_id,
                "path": "forms/my_form.form.yaml",
                "organization_id": org_id,
                "roles": [role_id],
                "access_level": "role_based",
            },
        },
        "agents": {},
        "apps": {},
    }


def test_parse_manifest_from_yaml(sample_manifest):
    """Parse a YAML string into a Manifest object."""
    from src.services.manifest import parse_manifest

    yaml_str = yaml.dump(sample_manifest, default_flow_style=False)
    manifest = parse_manifest(yaml_str)
    assert "my_workflow" in manifest.workflows
    assert manifest.workflows["my_workflow"].path == "workflows/my_workflow.py"
    assert manifest.workflows["my_workflow"].function_name == "my_workflow"
    assert manifest.workflows["my_workflow"].type == "workflow"


def test_serialize_manifest(sample_manifest):
    """Serialize a Manifest back to YAML string."""
    from src.services.manifest import parse_manifest, serialize_manifest

    yaml_str = yaml.dump(sample_manifest, default_flow_style=False)
    manifest = parse_manifest(yaml_str)
    output = serialize_manifest(manifest)
    # Should be valid YAML
    reparsed = yaml.safe_load(output)
    assert "workflows" in reparsed
    assert "my_workflow" in reparsed["workflows"]


def test_serialize_manifest_round_trip_stability(sample_manifest):
    """Serialize → parse → serialize should produce identical output (no false conflicts)."""
    from src.services.manifest import parse_manifest, serialize_manifest

    yaml_str = yaml.dump(sample_manifest, default_flow_style=False)
    manifest = parse_manifest(yaml_str)
    output1 = serialize_manifest(manifest)
    manifest2 = parse_manifest(output1)
    output2 = serialize_manifest(manifest2)
    assert output1 == output2, "Round-trip serialization must be stable"


def test_serialize_manifest_excludes_defaults():
    """Default-valued fields should be omitted from serialized YAML."""
    from src.services.manifest import parse_manifest, serialize_manifest

    yaml_str = """
workflows:
  wf1:
    id: "11111111-1111-1111-1111-111111111111"
    path: workflows/wf1.py
    function_name: wf1
"""
    manifest = parse_manifest(yaml_str)
    output = serialize_manifest(manifest)
    data = yaml.safe_load(output)
    wf = data["workflows"]["wf1"]
    # Required fields present
    assert wf["id"] == "11111111-1111-1111-1111-111111111111"
    assert wf["path"] == "workflows/wf1.py"
    assert wf["function_name"] == "wf1"
    # Default-valued fields should be absent
    assert "type" not in wf  # default is "workflow"
    assert "access_level" not in wf  # default is "role_based"
    assert "endpoint_enabled" not in wf  # default is False
    assert "timeout_seconds" not in wf  # default is 1800
    assert "roles" not in wf  # default is []
    assert "tags" not in wf  # default is []
    assert "organization_id" not in wf  # default is None


def test_validate_manifest_broken_ref(sample_manifest):
    """Detect broken cross-references."""
    from src.services.manifest import parse_manifest, validate_manifest

    # Form references a workflow UUID that exists — should be fine
    yaml_str = yaml.dump(sample_manifest, default_flow_style=False)
    manifest = parse_manifest(yaml_str)
    errors = validate_manifest(manifest)
    assert len(errors) == 0


def test_validate_manifest_missing_org(sample_manifest):
    """Detect reference to non-existent organization."""
    from src.services.manifest import parse_manifest, validate_manifest

    sample_manifest["workflows"]["my_workflow"]["organization_id"] = str(uuid4())
    yaml_str = yaml.dump(sample_manifest, default_flow_style=False)
    manifest = parse_manifest(yaml_str)
    errors = validate_manifest(manifest)
    assert any("organization" in e.lower() for e in errors)


def test_validate_manifest_missing_role(sample_manifest):
    """Detect reference to non-existent role."""
    from src.services.manifest import parse_manifest, validate_manifest

    sample_manifest["workflows"]["my_workflow"]["roles"] = [str(uuid4())]
    yaml_str = yaml.dump(sample_manifest, default_flow_style=False)
    manifest = parse_manifest(yaml_str)
    errors = validate_manifest(manifest)
    assert any("role" in e.lower() for e in errors)


def test_empty_manifest():
    """Empty manifest should parse without error."""
    from src.services.manifest import parse_manifest

    manifest = parse_manifest("")
    assert len(manifest.workflows) == 0
    assert len(manifest.forms) == 0


def test_get_entity_ids():
    """Get all entity UUIDs from manifest."""
    from src.services.manifest import parse_manifest, get_all_entity_ids

    yaml_str = """
workflows:
  wf1:
    id: "11111111-1111-1111-1111-111111111111"
    path: workflows/wf1.py
    function_name: wf1
    type: workflow
forms:
  form1:
    id: "22222222-2222-2222-2222-222222222222"
    path: forms/form1.form.yaml
"""
    manifest = parse_manifest(yaml_str)
    ids = get_all_entity_ids(manifest)
    assert "11111111-1111-1111-1111-111111111111" in ids
    assert "22222222-2222-2222-2222-222222222222" in ids


def test_get_paths():
    """Get all file paths from manifest."""
    from src.services.manifest import parse_manifest, get_all_paths

    yaml_str = """
workflows:
  wf1:
    id: "11111111-1111-1111-1111-111111111111"
    path: workflows/wf1.py
    function_name: wf1
    type: workflow
forms:
  form1:
    id: "22222222-2222-2222-2222-222222222222"
    path: forms/form1.form.yaml
"""
    manifest = parse_manifest(yaml_str)
    paths = get_all_paths(manifest)
    assert "workflows/wf1.py" in paths
    assert "forms/form1.form.yaml" in paths


# =============================================================================
# Split manifest (per-entity-type files) tests
# =============================================================================


class TestSerializeManifestDir:
    def test_produces_correct_files(self, sample_manifest):
        """serialize_manifest_dir produces one file per non-empty entity type."""
        from src.services.manifest import parse_manifest, serialize_manifest_dir

        yaml_str = yaml.dump(sample_manifest, default_flow_style=False)
        manifest = parse_manifest(yaml_str)
        files = serialize_manifest_dir(manifest)

        assert "organizations.yaml" in files
        assert "roles.yaml" in files
        assert "workflows.yaml" in files
        assert "forms.yaml" in files

        # Verify YAML content is correct
        wf_data = yaml.safe_load(files["workflows.yaml"])
        assert "workflows" in wf_data
        assert "my_workflow" in wf_data["workflows"]

        org_data = yaml.safe_load(files["organizations.yaml"])
        assert "organizations" in org_data
        assert len(org_data["organizations"]) == 1

    def test_skips_empty_entity_types(self):
        """Empty entity types should not produce files."""
        from src.services.manifest import Manifest, serialize_manifest_dir, ManifestWorkflow

        manifest = Manifest(
            workflows={
                "wf1": ManifestWorkflow(
                    id="11111111-1111-1111-1111-111111111111",
                    path="workflows/wf1.py",
                    function_name="wf1",
                )
            }
        )
        files = serialize_manifest_dir(manifest)

        assert "workflows.yaml" in files
        assert "forms.yaml" not in files
        assert "agents.yaml" not in files
        assert "apps.yaml" not in files
        assert "organizations.yaml" not in files
        assert "roles.yaml" not in files


class TestParseManifestDir:
    def test_round_trip(self, sample_manifest):
        """serialize_manifest_dir → parse_manifest_dir produces equivalent manifest."""
        from src.services.manifest import parse_manifest, serialize_manifest_dir, parse_manifest_dir

        yaml_str = yaml.dump(sample_manifest, default_flow_style=False)
        original = parse_manifest(yaml_str)
        files = serialize_manifest_dir(original)
        restored = parse_manifest_dir(files)

        assert len(restored.workflows) == len(original.workflows)
        assert len(restored.forms) == len(original.forms)
        assert len(restored.organizations) == len(original.organizations)
        assert len(restored.roles) == len(original.roles)

        for name in original.workflows:
            assert name in restored.workflows
            assert restored.workflows[name].id == original.workflows[name].id
            assert restored.workflows[name].path == original.workflows[name].path

    def test_missing_files(self):
        """Partial set of files should still work (missing = empty)."""
        from src.services.manifest import parse_manifest_dir

        files = {
            "workflows.yaml": """
workflows:
  wf1:
    id: "11111111-1111-1111-1111-111111111111"
    path: workflows/wf1.py
    function_name: wf1
"""
        }
        manifest = parse_manifest_dir(files)
        assert len(manifest.workflows) == 1
        assert len(manifest.forms) == 0
        assert len(manifest.agents) == 0
        assert len(manifest.apps) == 0


class TestReadWriteManifestDir:
    def test_write_and_read_split(self, tmp_path, sample_manifest):
        """write_manifest_to_dir → read_manifest_from_dir round-trip."""
        from src.services.manifest import (
            parse_manifest,
            write_manifest_to_dir,
            read_manifest_from_dir,
        )

        yaml_str = yaml.dump(sample_manifest, default_flow_style=False)
        original = parse_manifest(yaml_str)

        bifrost_dir = tmp_path / ".bifrost"
        write_manifest_to_dir(original, bifrost_dir)

        # Verify files on disk
        assert (bifrost_dir / "workflows.yaml").exists()
        assert (bifrost_dir / "forms.yaml").exists()
        assert (bifrost_dir / "organizations.yaml").exists()
        assert (bifrost_dir / "roles.yaml").exists()
        assert not (bifrost_dir / "metadata.yaml").exists()

        restored = read_manifest_from_dir(bifrost_dir)
        assert len(restored.workflows) == len(original.workflows)
        assert len(restored.forms) == len(original.forms)

    def test_write_cleans_legacy_file(self, tmp_path):
        """write_manifest_to_dir removes legacy metadata.yaml if present."""
        from src.services.manifest import Manifest, write_manifest_to_dir

        bifrost_dir = tmp_path / ".bifrost"
        bifrost_dir.mkdir()
        legacy = bifrost_dir / "metadata.yaml"
        legacy.write_text("workflows: {}")

        write_manifest_to_dir(Manifest(), bifrost_dir)

        assert not legacy.exists()

    def test_write_removes_stale_split_files(self, tmp_path):
        """write_manifest_to_dir removes split files for now-empty entity types."""
        from src.services.manifest import Manifest, ManifestWorkflow, write_manifest_to_dir

        bifrost_dir = tmp_path / ".bifrost"

        # Write with workflows
        manifest_with_wf = Manifest(
            workflows={
                "wf1": ManifestWorkflow(
                    id="11111111-1111-1111-1111-111111111111",
                    path="workflows/wf1.py",
                    function_name="wf1",
                )
            }
        )
        write_manifest_to_dir(manifest_with_wf, bifrost_dir)
        assert (bifrost_dir / "workflows.yaml").exists()

        # Write empty manifest — workflows.yaml should be removed
        write_manifest_to_dir(Manifest(), bifrost_dir)
        assert not (bifrost_dir / "workflows.yaml").exists()

    def test_read_split_format(self, tmp_path):
        """read_manifest_from_dir detects and reads split files."""
        from src.services.manifest import read_manifest_from_dir

        bifrost_dir = tmp_path / ".bifrost"
        bifrost_dir.mkdir()
        (bifrost_dir / "workflows.yaml").write_text("""
workflows:
  wf1:
    id: "11111111-1111-1111-1111-111111111111"
    path: workflows/wf1.py
    function_name: wf1
""")
        manifest = read_manifest_from_dir(bifrost_dir)
        assert "wf1" in manifest.workflows

    def test_read_legacy_format(self, tmp_path):
        """read_manifest_from_dir falls back to legacy metadata.yaml."""
        from src.services.manifest import read_manifest_from_dir

        bifrost_dir = tmp_path / ".bifrost"
        bifrost_dir.mkdir()
        (bifrost_dir / "metadata.yaml").write_text("""
workflows:
  wf1:
    id: "11111111-1111-1111-1111-111111111111"
    path: workflows/wf1.py
    function_name: wf1
""")
        manifest = read_manifest_from_dir(bifrost_dir)
        assert "wf1" in manifest.workflows

    def test_read_empty_directory(self, tmp_path):
        """Empty directory returns empty Manifest."""
        from src.services.manifest import read_manifest_from_dir

        bifrost_dir = tmp_path / ".bifrost"
        bifrost_dir.mkdir()
        manifest = read_manifest_from_dir(bifrost_dir)
        assert len(manifest.workflows) == 0
        assert len(manifest.forms) == 0

    def test_read_missing_directory(self, tmp_path):
        """Missing directory returns empty Manifest."""
        from src.services.manifest import read_manifest_from_dir

        manifest = read_manifest_from_dir(tmp_path / "nonexistent")
        assert len(manifest.workflows) == 0


# =============================================================================
# New entity types: Integrations, Configs, Tables, Knowledge, Events
# =============================================================================


@pytest.fixture
def full_manifest_data():
    """Manifest data with all entity types populated."""
    org_id = str(uuid4())
    role_id = str(uuid4())
    wf_id = str(uuid4())
    dp_wf_id = str(uuid4())  # data provider workflow
    form_id = str(uuid4())
    agent_id = str(uuid4())
    app_id = str(uuid4())
    integ_id = str(uuid4())
    config_id = str(uuid4())
    secret_config_id = str(uuid4())
    table_id = str(uuid4())
    oauth_token_id = str(uuid4())
    event_source_id = str(uuid4())
    event_sub_id = str(uuid4())

    return {
        "org_id": org_id,
        "role_id": role_id,
        "wf_id": wf_id,
        "dp_wf_id": dp_wf_id,
        "form_id": form_id,
        "agent_id": agent_id,
        "app_id": app_id,
        "integ_id": integ_id,
        "config_id": config_id,
        "secret_config_id": secret_config_id,
        "oauth_token_id": oauth_token_id,
        "table_id": table_id,
        "event_source_id": event_source_id,
        "event_sub_id": event_sub_id,
        "manifest": {
            "organizations": [{"id": org_id, "name": "TestOrg"}],
            "roles": [{"id": role_id, "name": "admin"}],
            "workflows": {
                "my_workflow": {
                    "id": wf_id,
                    "path": "workflows/my_workflow.py",
                    "function_name": "my_workflow",
                },
                "list_entities_dp": {
                    "id": dp_wf_id,
                    "path": "workflows/list_entities_dp.py",
                    "function_name": "list_entities_dp",
                    "type": "data_provider",
                },
            },
            "integrations": {
                "HaloPSA": {
                    "id": integ_id,
                    "entity_id": "tenant_id",
                    "entity_id_name": "Tenant",
                    "default_entity_id": "default-tenant",
                    "list_entities_data_provider_id": dp_wf_id,
                    "config_schema": [
                        {
                            "key": "api_url",
                            "type": "string",
                            "required": True,
                            "description": "HaloPSA API URL",
                            "position": 0,
                        },
                        {
                            "key": "api_key",
                            "type": "secret",
                            "required": True,
                            "description": "API Key",
                            "position": 1,
                        },
                    ],
                    "oauth_provider": {
                        "provider_name": "halopsa",
                        "display_name": "HaloPSA OAuth",
                        "oauth_flow_type": "client_credentials",
                        "client_id": "__NEEDS_SETUP__",
                        "authorization_url": "https://halo.example.com/auth",
                        "token_url": "https://halo.example.com/token",
                        "scopes": ["all"],
                    },
                    "mappings": [
                        {
                            "organization_id": org_id,
                            "entity_id": "tenant-123",
                            "entity_name": "My Tenant",
                            "oauth_token_id": oauth_token_id,
                        },
                    ],
                },
            },
            "configs": {
                config_id: {
                    "id": config_id,
                    "integration_id": integ_id,
                    "key": "halopsa/api_url",
                    "config_type": "string",
                    "description": "HaloPSA API URL",
                    "organization_id": org_id,
                    "value": "https://api.halopsa.com",
                },
                secret_config_id: {
                    "id": secret_config_id,
                    "integration_id": integ_id,
                    "key": "halopsa/api_key",
                    "config_type": "secret",
                    "description": "API Key",
                    "organization_id": org_id,
                    "value": None,
                },
            },
            "tables": {
                "ticket_cache": {
                    "id": table_id,
                    "description": "Cached ticket data",
                    "organization_id": org_id,
                    "application_id": app_id,
                    "schema": {
                        "columns": [
                            {"name": "ticket_id", "type": "string"},
                            {"name": "subject", "type": "string"},
                        ]
                    },
                },
            },
            "events": {
                "Ticket Webhook": {
                    "id": event_source_id,
                    "source_type": "webhook",
                    "organization_id": org_id,
                    "is_active": True,
                    "adapter_name": "halopsa",
                    "webhook_integration_id": integ_id,
                    "webhook_config": {"verify_ssl": True},
                    "subscriptions": [
                        {
                            "id": event_sub_id,
                            "workflow_id": wf_id,
                            "event_type": "ticket.created",
                            "input_mapping": {"ticket_id": "$.data.id"},
                            "is_active": True,
                        },
                    ],
                },
            },
            "forms": {
                "my_form": {
                    "id": form_id,
                    "path": "forms/my_form.form.yaml",
                    "organization_id": org_id,
                    "roles": [role_id],
                },
            },
            "agents": {
                "my_agent": {
                    "id": agent_id,
                    "path": "agents/my_agent.agent.yaml",
                    "organization_id": org_id,
                    "roles": [role_id],
                },
            },
            "apps": {
                "my_app": {
                    "id": app_id,
                    "path": "apps/my-app",
                    "name": "My App",
                    "description": "Test app",
                    "dependencies": {"recharts": "2.12"},
                    "organization_id": org_id,
                    "roles": [role_id],
                },
            },
        },
    }


class TestIntegrationManifest:
    """Tests for integration manifest models."""

    def test_parse_integration(self, full_manifest_data):
        """Parse integration with config_schema, oauth, and mappings."""
        from src.services.manifest import parse_manifest

        yaml_str = yaml.dump(full_manifest_data["manifest"], default_flow_style=False)
        manifest = parse_manifest(yaml_str)

        assert "HaloPSA" in manifest.integrations
        integ = manifest.integrations["HaloPSA"]
        assert integ.id == full_manifest_data["integ_id"]
        assert integ.entity_id == "tenant_id"
        assert integ.entity_id_name == "Tenant"
        assert integ.default_entity_id == "default-tenant"
        assert integ.list_entities_data_provider_id == full_manifest_data["dp_wf_id"]

        # Config schema
        assert len(integ.config_schema) == 2
        assert integ.config_schema[0].key == "api_url"
        assert integ.config_schema[0].type == "string"
        assert integ.config_schema[0].required is True
        assert integ.config_schema[1].key == "api_key"
        assert integ.config_schema[1].type == "secret"

        # OAuth provider
        assert integ.oauth_provider is not None
        assert integ.oauth_provider.provider_name == "halopsa"
        assert integ.oauth_provider.oauth_flow_type == "client_credentials"
        assert integ.oauth_provider.client_id == "__NEEDS_SETUP__"
        assert integ.oauth_provider.scopes == ["all"]

        # Mappings
        assert len(integ.mappings) == 1
        assert integ.mappings[0].entity_id == "tenant-123"
        assert integ.mappings[0].organization_id == full_manifest_data["org_id"]
        assert integ.mappings[0].oauth_token_id == full_manifest_data["oauth_token_id"]

    def test_integration_round_trip(self, full_manifest_data):
        """Integration survives serialize → parse round-trip."""
        from src.services.manifest import parse_manifest, serialize_manifest

        yaml_str = yaml.dump(full_manifest_data["manifest"], default_flow_style=False)
        original = parse_manifest(yaml_str)
        output = serialize_manifest(original)
        restored = parse_manifest(output)

        integ_orig = original.integrations["HaloPSA"]
        integ_rest = restored.integrations["HaloPSA"]
        assert integ_rest.id == integ_orig.id
        assert integ_rest.entity_id == integ_orig.entity_id
        assert len(integ_rest.config_schema) == len(integ_orig.config_schema)
        assert integ_rest.oauth_provider is not None
        assert integ_orig.oauth_provider is not None
        assert integ_rest.oauth_provider.provider_name == integ_orig.oauth_provider.provider_name
        assert len(integ_rest.mappings) == len(integ_orig.mappings)

    def test_integration_defaults_omitted(self):
        """Integration with defaults only serializes non-default fields."""
        from src.services.manifest import Manifest, ManifestIntegration, serialize_manifest

        manifest = Manifest(
            integrations={
                "bare": ManifestIntegration(id="11111111-1111-1111-1111-111111111111")
            }
        )
        output = serialize_manifest(manifest)
        data = yaml.safe_load(output)
        integ = data["integrations"]["bare"]
        assert integ["id"] == "11111111-1111-1111-1111-111111111111"
        assert "config_schema" not in integ
        assert "oauth_provider" not in integ
        assert "mappings" not in integ
        assert "entity_id" not in integ

    def test_mapping_oauth_token_id_round_trip(self):
        """Mapping oauth_token_id survives serialize → parse round-trip."""
        from src.services.manifest import (
            Manifest, ManifestIntegration, ManifestIntegrationMapping,
            serialize_manifest, parse_manifest,
        )

        token_id = str(uuid4())
        manifest = Manifest(
            integrations={
                "TestInteg": ManifestIntegration(
                    id=str(uuid4()),
                    mappings=[
                        ManifestIntegrationMapping(
                            entity_id="tenant-1",
                            oauth_token_id=token_id,
                        ),
                    ],
                ),
            },
        )
        output = serialize_manifest(manifest)
        restored = parse_manifest(output)
        assert restored.integrations["TestInteg"].mappings[0].oauth_token_id == token_id

    def test_integration_split_file(self, full_manifest_data):
        """Integrations serialize to integrations.yaml in split format."""
        from src.services.manifest import parse_manifest, serialize_manifest_dir, parse_manifest_dir

        yaml_str = yaml.dump(full_manifest_data["manifest"], default_flow_style=False)
        manifest = parse_manifest(yaml_str)
        files = serialize_manifest_dir(manifest)

        assert "integrations.yaml" in files
        integ_data = yaml.safe_load(files["integrations.yaml"])
        assert "integrations" in integ_data
        assert "HaloPSA" in integ_data["integrations"]

        # Round-trip through split format
        restored = parse_manifest_dir(files)
        assert "HaloPSA" in restored.integrations
        assert restored.integrations["HaloPSA"].id == full_manifest_data["integ_id"]


class TestConfigManifest:
    """Tests for config manifest models."""

    def test_parse_config(self, full_manifest_data):
        """Parse config entries including secret redaction."""
        from src.services.manifest import parse_manifest

        yaml_str = yaml.dump(full_manifest_data["manifest"], default_flow_style=False)
        manifest = parse_manifest(yaml_str)

        config_id = full_manifest_data["config_id"]
        secret_config_id = full_manifest_data["secret_config_id"]

        assert config_id in manifest.configs
        cfg = manifest.configs[config_id]
        assert cfg.id == config_id
        assert cfg.config_type == "string"
        assert cfg.value == "https://api.halopsa.com"
        assert cfg.integration_id == full_manifest_data["integ_id"]
        assert cfg.organization_id == full_manifest_data["org_id"]

        # Secret config has null value
        secret_cfg = manifest.configs[secret_config_id]
        assert secret_cfg.config_type == "secret"
        assert secret_cfg.value is None

    def test_config_round_trip(self, full_manifest_data):
        """Configs survive serialize → parse round-trip."""
        from src.services.manifest import parse_manifest, serialize_manifest

        yaml_str = yaml.dump(full_manifest_data["manifest"], default_flow_style=False)
        original = parse_manifest(yaml_str)
        output = serialize_manifest(original)
        restored = parse_manifest(output)

        assert len(restored.configs) == len(original.configs)
        for key in original.configs:
            assert key in restored.configs
            assert restored.configs[key].id == original.configs[key].id
            assert restored.configs[key].config_type == original.configs[key].config_type

    def test_config_split_file(self, full_manifest_data):
        """Configs serialize to configs.yaml in split format."""
        from src.services.manifest import parse_manifest, serialize_manifest_dir

        yaml_str = yaml.dump(full_manifest_data["manifest"], default_flow_style=False)
        manifest = parse_manifest(yaml_str)
        files = serialize_manifest_dir(manifest)

        assert "configs.yaml" in files
        cfg_data = yaml.safe_load(files["configs.yaml"])
        assert "configs" in cfg_data
        assert full_manifest_data["config_id"] in cfg_data["configs"]


class TestTableManifest:
    """Tests for table manifest models with schema alias."""

    def test_parse_table_with_schema_alias(self, full_manifest_data):
        """Parse table with 'schema' alias → table_schema field."""
        from src.services.manifest import parse_manifest

        yaml_str = yaml.dump(full_manifest_data["manifest"], default_flow_style=False)
        manifest = parse_manifest(yaml_str)

        assert "ticket_cache" in manifest.tables
        table = manifest.tables["ticket_cache"]
        assert table.id == full_manifest_data["table_id"]
        assert table.description == "Cached ticket data"
        assert table.organization_id == full_manifest_data["org_id"]
        assert table.application_id == full_manifest_data["app_id"]
        assert table.table_schema is not None
        assert "columns" in table.table_schema
        assert len(table.table_schema["columns"]) == 2

    def test_table_serializes_as_schema(self, full_manifest_data):
        """Table serializes table_schema as 'schema' in YAML (via alias)."""
        from src.services.manifest import parse_manifest, serialize_manifest

        yaml_str = yaml.dump(full_manifest_data["manifest"], default_flow_style=False)
        manifest = parse_manifest(yaml_str)
        output = serialize_manifest(manifest)
        data = yaml.safe_load(output)

        table_data = data["tables"]["ticket_cache"]
        assert "schema" in table_data
        assert "table_schema" not in table_data

    def test_table_round_trip(self, full_manifest_data):
        """Tables survive serialize → parse round-trip (alias preserved)."""
        from src.services.manifest import parse_manifest, serialize_manifest

        yaml_str = yaml.dump(full_manifest_data["manifest"], default_flow_style=False)
        original = parse_manifest(yaml_str)
        output = serialize_manifest(original)
        restored = parse_manifest(output)

        assert "ticket_cache" in restored.tables
        assert restored.tables["ticket_cache"].table_schema == original.tables["ticket_cache"].table_schema

    def test_table_split_file(self, full_manifest_data):
        """Tables serialize to tables.yaml in split format."""
        from src.services.manifest import parse_manifest, serialize_manifest_dir

        yaml_str = yaml.dump(full_manifest_data["manifest"], default_flow_style=False)
        manifest = parse_manifest(yaml_str)
        files = serialize_manifest_dir(manifest)

        assert "tables.yaml" in files
        table_data = yaml.safe_load(files["tables.yaml"])
        assert "tables" in table_data
        assert "ticket_cache" in table_data["tables"]
        # Alias should appear in YAML
        assert "schema" in table_data["tables"]["ticket_cache"]


class TestEventManifest:
    """Tests for event source + subscription manifest models."""

    def test_parse_event_source(self, full_manifest_data):
        """Parse event source with nested subscriptions."""
        from src.services.manifest import parse_manifest

        yaml_str = yaml.dump(full_manifest_data["manifest"], default_flow_style=False)
        manifest = parse_manifest(yaml_str)

        assert "Ticket Webhook" in manifest.events
        evt = manifest.events["Ticket Webhook"]
        assert evt.id == full_manifest_data["event_source_id"]
        assert evt.source_type == "webhook"
        assert evt.organization_id == full_manifest_data["org_id"]
        assert evt.adapter_name == "halopsa"
        assert evt.webhook_integration_id == full_manifest_data["integ_id"]
        assert evt.webhook_config == {"verify_ssl": True}

        # Subscriptions
        assert len(evt.subscriptions) == 1
        sub = evt.subscriptions[0]
        assert sub.id == full_manifest_data["event_sub_id"]
        assert sub.workflow_id == full_manifest_data["wf_id"]
        assert sub.event_type == "ticket.created"
        assert sub.input_mapping == {"ticket_id": "$.data.id"}
        assert sub.is_active is True

    def test_schedule_event_source(self):
        """Parse a schedule-type event source."""
        from src.services.manifest import parse_manifest

        wf_id = str(uuid4())
        sub_id = str(uuid4())
        es_id = str(uuid4())
        yaml_str = yaml.dump({
            "workflows": {
                "sync_job": {
                    "id": wf_id,
                    "path": "workflows/sync_job.py",
                    "function_name": "sync_job",
                },
            },
            "events": {
                "Daily Sync": {
                    "id": es_id,
                    "source_type": "schedule",
                    "cron_expression": "0 6 * * *",
                    "timezone": "America/New_York",
                    "schedule_enabled": True,
                    "subscriptions": [
                        {
                            "id": sub_id,
                            "workflow_id": wf_id,
                        },
                    ],
                },
            },
        }, default_flow_style=False)
        manifest = parse_manifest(yaml_str)

        evt = manifest.events["Daily Sync"]
        assert evt.source_type == "schedule"
        assert evt.cron_expression == "0 6 * * *"
        assert evt.timezone == "America/New_York"
        assert evt.schedule_enabled is True
        assert len(evt.subscriptions) == 1

    def test_event_round_trip(self, full_manifest_data):
        """Events survive serialize → parse round-trip."""
        from src.services.manifest import parse_manifest, serialize_manifest

        yaml_str = yaml.dump(full_manifest_data["manifest"], default_flow_style=False)
        original = parse_manifest(yaml_str)
        output = serialize_manifest(original)
        restored = parse_manifest(output)

        assert "Ticket Webhook" in restored.events
        evt_orig = original.events["Ticket Webhook"]
        evt_rest = restored.events["Ticket Webhook"]
        assert evt_rest.id == evt_orig.id
        assert evt_rest.source_type == evt_orig.source_type
        assert len(evt_rest.subscriptions) == len(evt_orig.subscriptions)
        assert evt_rest.subscriptions[0].workflow_id == evt_orig.subscriptions[0].workflow_id

    def test_event_split_file(self, full_manifest_data):
        """Events serialize to events.yaml in split format."""
        from src.services.manifest import parse_manifest, serialize_manifest_dir, parse_manifest_dir

        yaml_str = yaml.dump(full_manifest_data["manifest"], default_flow_style=False)
        manifest = parse_manifest(yaml_str)
        files = serialize_manifest_dir(manifest)

        assert "events.yaml" in files
        evt_data = yaml.safe_load(files["events.yaml"])
        assert "events" in evt_data
        assert "Ticket Webhook" in evt_data["events"]

        # Round-trip split
        restored = parse_manifest_dir(files)
        assert "Ticket Webhook" in restored.events
        assert len(restored.events["Ticket Webhook"].subscriptions) == 1


class TestFullManifestSplitRoundTrip:
    """Test full manifest with all entity types through split format."""

    def test_all_entity_types_round_trip(self, full_manifest_data):
        """All entity types survive write_manifest_to_dir → read_manifest_from_dir."""
        from src.services.manifest import (
            parse_manifest,
            write_manifest_to_dir,
            read_manifest_from_dir,
        )

        yaml_str = yaml.dump(full_manifest_data["manifest"], default_flow_style=False)
        original = parse_manifest(yaml_str)

        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            bifrost_dir = Path(tmpdir) / ".bifrost"
            write_manifest_to_dir(original, bifrost_dir)

            # Verify all expected files exist
            assert (bifrost_dir / "organizations.yaml").exists()
            assert (bifrost_dir / "roles.yaml").exists()
            assert (bifrost_dir / "workflows.yaml").exists()
            assert (bifrost_dir / "integrations.yaml").exists()
            assert (bifrost_dir / "configs.yaml").exists()
            assert (bifrost_dir / "tables.yaml").exists()
            assert (bifrost_dir / "events.yaml").exists()
            assert (bifrost_dir / "forms.yaml").exists()
            assert (bifrost_dir / "agents.yaml").exists()
            assert (bifrost_dir / "apps.yaml").exists()

            restored = read_manifest_from_dir(bifrost_dir)

        assert len(restored.organizations) == len(original.organizations)
        assert len(restored.roles) == len(original.roles)
        assert len(restored.workflows) == len(original.workflows)
        assert len(restored.integrations) == len(original.integrations)
        assert len(restored.configs) == len(original.configs)
        assert len(restored.tables) == len(original.tables)
        assert len(restored.events) == len(original.events)
        assert len(restored.forms) == len(original.forms)
        assert len(restored.agents) == len(original.agents)
        assert len(restored.apps) == len(original.apps)


class TestValidateManifestNewTypes:
    """Validation tests for cross-references in new entity types."""

    def test_valid_full_manifest(self, full_manifest_data):
        """Full manifest with correct references passes validation."""
        from src.services.manifest import parse_manifest, validate_manifest

        yaml_str = yaml.dump(full_manifest_data["manifest"], default_flow_style=False)
        manifest = parse_manifest(yaml_str)
        errors = validate_manifest(manifest)
        assert errors == []

    def test_integration_bad_data_provider_ref(self, full_manifest_data):
        """Integration referencing unknown data provider workflow is caught."""
        from src.services.manifest import parse_manifest, validate_manifest

        data = full_manifest_data["manifest"]
        data["integrations"]["HaloPSA"]["list_entities_data_provider_id"] = str(uuid4())
        yaml_str = yaml.dump(data, default_flow_style=False)
        manifest = parse_manifest(yaml_str)
        errors = validate_manifest(manifest)
        assert any("data provider" in e.lower() for e in errors)

    def test_integration_bad_mapping_org_ref(self, full_manifest_data):
        """Integration mapping referencing unknown org is caught."""
        from src.services.manifest import parse_manifest, validate_manifest

        data = full_manifest_data["manifest"]
        data["integrations"]["HaloPSA"]["mappings"][0]["organization_id"] = str(uuid4())
        yaml_str = yaml.dump(data, default_flow_style=False)
        manifest = parse_manifest(yaml_str)
        errors = validate_manifest(manifest)
        assert any("organization" in e.lower() for e in errors)

    def test_config_bad_integration_ref(self, full_manifest_data):
        """Config referencing unknown integration is caught."""
        from src.services.manifest import parse_manifest, validate_manifest

        data = full_manifest_data["manifest"]
        config_id = full_manifest_data["config_id"]
        data["configs"][config_id]["integration_id"] = str(uuid4())
        yaml_str = yaml.dump(data, default_flow_style=False)
        manifest = parse_manifest(yaml_str)
        errors = validate_manifest(manifest)
        assert any("integration" in e.lower() for e in errors)

    def test_config_bad_org_ref(self, full_manifest_data):
        """Config referencing unknown organization is caught."""
        from src.services.manifest import parse_manifest, validate_manifest

        data = full_manifest_data["manifest"]
        config_id = full_manifest_data["config_id"]
        data["configs"][config_id]["organization_id"] = str(uuid4())
        yaml_str = yaml.dump(data, default_flow_style=False)
        manifest = parse_manifest(yaml_str)
        errors = validate_manifest(manifest)
        assert any("organization" in e.lower() for e in errors)

    def test_table_bad_org_ref(self, full_manifest_data):
        """Table referencing unknown org is caught."""
        from src.services.manifest import parse_manifest, validate_manifest

        data = full_manifest_data["manifest"]
        data["tables"]["ticket_cache"]["organization_id"] = str(uuid4())
        yaml_str = yaml.dump(data, default_flow_style=False)
        manifest = parse_manifest(yaml_str)
        errors = validate_manifest(manifest)
        assert any("organization" in e.lower() for e in errors)

    def test_table_bad_app_ref(self, full_manifest_data):
        """Table referencing unknown application is caught."""
        from src.services.manifest import parse_manifest, validate_manifest

        data = full_manifest_data["manifest"]
        data["tables"]["ticket_cache"]["application_id"] = str(uuid4())
        yaml_str = yaml.dump(data, default_flow_style=False)
        manifest = parse_manifest(yaml_str)
        errors = validate_manifest(manifest)
        assert any("application" in e.lower() for e in errors)

    def test_event_bad_org_ref(self, full_manifest_data):
        """Event source referencing unknown org is caught."""
        from src.services.manifest import parse_manifest, validate_manifest

        data = full_manifest_data["manifest"]
        data["events"]["Ticket Webhook"]["organization_id"] = str(uuid4())
        yaml_str = yaml.dump(data, default_flow_style=False)
        manifest = parse_manifest(yaml_str)
        errors = validate_manifest(manifest)
        assert any("organization" in e.lower() for e in errors)

    def test_event_bad_webhook_integration_ref(self, full_manifest_data):
        """Event source referencing unknown webhook integration is caught."""
        from src.services.manifest import parse_manifest, validate_manifest

        data = full_manifest_data["manifest"]
        data["events"]["Ticket Webhook"]["webhook_integration_id"] = str(uuid4())
        yaml_str = yaml.dump(data, default_flow_style=False)
        manifest = parse_manifest(yaml_str)
        errors = validate_manifest(manifest)
        assert any("integration" in e.lower() for e in errors)

    def test_event_sub_bad_workflow_ref(self, full_manifest_data):
        """Event subscription referencing unknown workflow is caught."""
        from src.services.manifest import parse_manifest, validate_manifest

        data = full_manifest_data["manifest"]
        data["events"]["Ticket Webhook"]["subscriptions"][0]["workflow_id"] = str(uuid4())
        yaml_str = yaml.dump(data, default_flow_style=False)
        manifest = parse_manifest(yaml_str)
        errors = validate_manifest(manifest)
        assert any("workflow" in e.lower() for e in errors)


class TestConfigDictKeyCollision:
    """Verify configs with same key name but different scopes don't collide."""

    def test_configs_with_same_key_different_orgs_survive_round_trip(self):
        """Two configs with same key but different org_ids both survive serialization."""
        from src.services.manifest import Manifest, ManifestConfig, serialize_manifest, parse_manifest

        config_id_1 = str(uuid4())
        config_id_2 = str(uuid4())
        org_id_1 = str(uuid4())
        org_id_2 = str(uuid4())
        integ_id = str(uuid4())

        manifest = Manifest(
            configs={
                config_id_1: ManifestConfig(
                    id=config_id_1,
                    integration_id=integ_id,
                    key="api_url",
                    config_type="string",
                    organization_id=org_id_1,
                    value="https://org1.example.com",
                ),
                config_id_2: ManifestConfig(
                    id=config_id_2,
                    integration_id=integ_id,
                    key="api_url",
                    config_type="string",
                    organization_id=org_id_2,
                    value="https://org2.example.com",
                ),
            },
        )
        output = serialize_manifest(manifest)
        restored = parse_manifest(output)

        assert len(restored.configs) == 2
        assert config_id_1 in restored.configs
        assert config_id_2 in restored.configs
        assert restored.configs[config_id_1].value == "https://org1.example.com"
        assert restored.configs[config_id_2].value == "https://org2.example.com"


class TestGetAllEntityIdsNewTypes:
    """Test that get_all_entity_ids includes all new entity types."""

    def test_includes_new_entity_ids(self, full_manifest_data):
        """get_all_entity_ids includes integrations, configs, tables, events, subscriptions."""
        from src.services.manifest import parse_manifest, get_all_entity_ids

        yaml_str = yaml.dump(full_manifest_data["manifest"], default_flow_style=False)
        manifest = parse_manifest(yaml_str)
        ids = get_all_entity_ids(manifest)

        # Existing types
        assert full_manifest_data["wf_id"] in ids
        assert full_manifest_data["form_id"] in ids
        assert full_manifest_data["agent_id"] in ids
        assert full_manifest_data["app_id"] in ids

        # New types
        assert full_manifest_data["integ_id"] in ids
        assert full_manifest_data["config_id"] in ids
        assert full_manifest_data["secret_config_id"] in ids
        assert full_manifest_data["table_id"] in ids
        assert full_manifest_data["event_source_id"] in ids
        assert full_manifest_data["event_sub_id"] in ids


class TestManifestSchemaCoverage:
    """Verify that all DB columns are either tracked in manifest models or explicitly ignored.

    When a developer adds a new column to an integration ORM model, this test
    forces them to decide: is this field managed by git (add to manifest model)
    or managed exclusively by the UI/runtime (add to the ignored set)?
    """

    # Columns that are intentionally NOT in the manifest — either internal
    # bookkeeping or UI-managed state.
    INTEGRATION_IGNORED = {
        "id",            # manifest uses dict key (name) for identity; id is a field inside
        "name",          # used as the manifest dict key, not a model field
        "is_deleted",    # soft-delete flag, internal
        "created_at",
        "updated_at",
    }

    CONFIG_SCHEMA_IGNORED = {
        "id",              # DB surrogate key, not in manifest
        "integration_id",  # implicit from parent integration
        "created_at",
        "updated_at",
    }

    MAPPING_IGNORED = {
        "id",              # DB surrogate key
        "integration_id",  # implicit from parent integration
        "created_at",
        "updated_at",
    }

    def test_integration_columns_tracked(self):
        """All Integration DB columns are in ManifestIntegration or explicitly ignored."""
        from sqlalchemy import inspect as sa_inspect
        from src.models.orm.integrations import Integration
        from src.services.manifest import ManifestIntegration

        db_columns = {c.name for c in sa_inspect(Integration).columns}
        manifest_fields = set(ManifestIntegration.model_fields.keys())
        untracked = db_columns - manifest_fields - self.INTEGRATION_IGNORED
        assert not untracked, (
            f"New Integration DB columns not tracked in manifest or ignored: {untracked}. "
            "Add them to ManifestIntegration or to INTEGRATION_IGNORED in this test."
        )

    def test_config_schema_columns_tracked(self):
        """All IntegrationConfigSchema DB columns are in ManifestIntegrationConfigSchema or ignored."""
        from sqlalchemy import inspect as sa_inspect
        from src.models.orm.integrations import IntegrationConfigSchema
        from src.services.manifest import ManifestIntegrationConfigSchema

        db_columns = {c.name for c in sa_inspect(IntegrationConfigSchema).columns}
        manifest_fields = set(ManifestIntegrationConfigSchema.model_fields.keys())
        untracked = db_columns - manifest_fields - self.CONFIG_SCHEMA_IGNORED
        assert not untracked, (
            f"New IntegrationConfigSchema DB columns not tracked in manifest or ignored: {untracked}. "
            "Add them to ManifestIntegrationConfigSchema or to CONFIG_SCHEMA_IGNORED in this test."
        )

    def test_mapping_columns_tracked(self):
        """All IntegrationMapping DB columns are in ManifestIntegrationMapping or ignored."""
        from sqlalchemy import inspect as sa_inspect
        from src.models.orm.integrations import IntegrationMapping
        from src.services.manifest import ManifestIntegrationMapping

        db_columns = {c.name for c in sa_inspect(IntegrationMapping).columns}
        manifest_fields = set(ManifestIntegrationMapping.model_fields.keys())
        untracked = db_columns - manifest_fields - self.MAPPING_IGNORED
        assert not untracked, (
            f"New IntegrationMapping DB columns not tracked in manifest or ignored: {untracked}. "
            "Add them to ManifestIntegrationMapping or to MAPPING_IGNORED in this test."
        )
