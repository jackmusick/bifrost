"""
Manifest parser for .bifrost/ metadata files.

Provides Pydantic models and functions for reading, writing, and validating
the workspace manifest. The manifest declares all platform entities,
their file paths, UUIDs, org bindings, roles, and runtime config.

Supports both split format (one file per entity type in .bifrost/) and
legacy single-file format (.bifrost/metadata.yaml).

Stateless — no DB or S3 dependency.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

MANIFEST_FILES: dict[str, str] = {
    "organizations": "organizations.yaml",
    "roles": "roles.yaml",
    "workflows": "workflows.yaml",
    "integrations": "integrations.yaml",
    "configs": "configs.yaml",
    "tables": "tables.yaml",
    "knowledge": "knowledge.yaml",
    "events": "events.yaml",
    "forms": "forms.yaml",
    "agents": "agents.yaml",
    "apps": "apps.yaml",
}
MANIFEST_LEGACY_FILE = "metadata.yaml"


# =============================================================================
# Pydantic Models
# =============================================================================


class ManifestOrganization(BaseModel):
    """Organization entry in manifest."""
    id: str
    name: str


class ManifestRole(BaseModel):
    """Role entry in manifest."""
    id: str
    name: str
    organization_id: str | None = None


class ManifestWorkflow(BaseModel):
    """Workflow entry in manifest."""
    id: str
    path: str
    function_name: str
    type: str = "workflow"  # workflow | tool | data_provider
    organization_id: str | None = None
    roles: list[str] = Field(default_factory=list)  # Role UUIDs
    access_level: str = "role_based"
    endpoint_enabled: bool = False
    timeout_seconds: int = 1800
    public_endpoint: bool = False
    # Additional optional config
    category: str = "General"
    tags: list[str] = Field(default_factory=list)


class ManifestForm(BaseModel):
    """Form entry in manifest."""
    id: str
    path: str
    organization_id: str | None = None
    roles: list[str] = Field(default_factory=list)
    access_level: str = "role_based"


class ManifestAgent(BaseModel):
    """Agent entry in manifest."""
    id: str
    path: str
    organization_id: str | None = None
    roles: list[str] = Field(default_factory=list)
    access_level: str = "role_based"


class ManifestApp(BaseModel):
    """App entry in manifest."""
    id: str
    path: str
    slug: str | None = None
    organization_id: str | None = None
    roles: list[str] = Field(default_factory=list)
    access_level: str = "authenticated"


# -- New entity types for manifest expansion --


class ManifestIntegrationConfigSchema(BaseModel):
    """Config schema item within an integration."""
    key: str
    type: str  # string, int, bool, json, secret
    required: bool = False
    description: str | None = None
    options: list[str] | None = None
    position: int = 0


class ManifestOAuthProvider(BaseModel):
    """OAuth provider structure within an integration.

    client_id uses "__NEEDS_SETUP__" sentinel for new instances.
    client_secret is never serialized.
    """
    provider_name: str
    display_name: str | None = None
    oauth_flow_type: str = "authorization_code"
    client_id: str = "__NEEDS_SETUP__"
    authorization_url: str | None = None
    token_url: str | None = None
    token_url_defaults: dict | None = None
    scopes: list[str] = Field(default_factory=list)
    redirect_uri: str | None = None


class ManifestIntegrationMapping(BaseModel):
    """Integration mapping to an org + external entity."""
    organization_id: str | None = None
    entity_id: str
    entity_name: str | None = None


class ManifestIntegration(BaseModel):
    """Integration entry in manifest."""
    id: str
    entity_id: str | None = None
    entity_id_name: str | None = None
    default_entity_id: str | None = None
    list_entities_data_provider_id: str | None = None  # workflow UUID
    config_schema: list[ManifestIntegrationConfigSchema] = Field(default_factory=list)
    oauth_provider: ManifestOAuthProvider | None = None
    mappings: list[ManifestIntegrationMapping] = Field(default_factory=list)


class ManifestConfig(BaseModel):
    """Config entry in manifest."""
    id: str
    integration_id: str | None = None
    key: str
    config_type: str = "string"
    description: str | None = None
    organization_id: str | None = None
    value: object | None = None  # None for SECRET type


class ManifestTable(BaseModel):
    """Table entry in manifest.

    Uses ``table_schema`` in Python but serializes as ``schema`` in YAML
    via the alias, matching the DB column name.
    """
    id: str
    description: str | None = None
    organization_id: str | None = None
    application_id: str | None = None
    table_schema: dict | None = Field(default=None, alias="schema")

    model_config = {"populate_by_name": True}


class ManifestKnowledgeNamespace(BaseModel):
    """Knowledge namespace declaration (declarative only — no DB entity)."""
    description: str | None = None
    organization_id: str | None = None
    roles: list[str] = Field(default_factory=list)  # Role UUIDs


class ManifestEventSubscription(BaseModel):
    """Event subscription within an event source."""
    id: str
    workflow_id: str
    event_type: str | None = None
    filter_expression: str | None = None
    input_mapping: dict | None = None
    is_active: bool = True


class ManifestEventSource(BaseModel):
    """Event source entry in manifest."""
    id: str
    source_type: str  # webhook, schedule, internal
    organization_id: str | None = None
    is_active: bool = True
    # Schedule config
    cron_expression: str | None = None
    timezone: str | None = None
    schedule_enabled: bool | None = None
    # Webhook config
    adapter_name: str | None = None
    webhook_integration_id: str | None = None  # integration UUID
    webhook_config: dict | None = None
    # Subscriptions
    subscriptions: list[ManifestEventSubscription] = Field(default_factory=list)


class Manifest(BaseModel):
    """The complete workspace manifest."""
    organizations: list[ManifestOrganization] = Field(default_factory=list)
    roles: list[ManifestRole] = Field(default_factory=list)
    workflows: dict[str, ManifestWorkflow] = Field(default_factory=dict)
    integrations: dict[str, ManifestIntegration] = Field(default_factory=dict)
    configs: dict[str, ManifestConfig] = Field(default_factory=dict)
    tables: dict[str, ManifestTable] = Field(default_factory=dict)
    knowledge: dict[str, ManifestKnowledgeNamespace] = Field(default_factory=dict)
    events: dict[str, ManifestEventSource] = Field(default_factory=dict)
    forms: dict[str, ManifestForm] = Field(default_factory=dict)
    agents: dict[str, ManifestAgent] = Field(default_factory=dict)
    apps: dict[str, ManifestApp] = Field(default_factory=dict)


# =============================================================================
# Parse / Serialize
# =============================================================================


def parse_manifest(yaml_str: str) -> Manifest:
    """Parse a YAML string into a Manifest object."""
    if not yaml_str or not yaml_str.strip():
        return Manifest()

    data = yaml.safe_load(yaml_str)
    if not data or not isinstance(data, dict):
        return Manifest()

    return Manifest(**data)


def serialize_manifest(manifest: Manifest) -> str:
    """Serialize a Manifest object to a YAML string.

    Uses exclude_defaults=True so that fields at their default values
    (empty lists, default strings, None) are omitted.  This keeps the
    output stable — re-serializing the same logical manifest always
    produces the same bytes, avoiding false conflicts during sync.
    """
    data = manifest.model_dump(mode="json", exclude_defaults=True, by_alias=True)
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


# =============================================================================
# Split-file serialize / parse
# =============================================================================


def serialize_manifest_dir(manifest: Manifest) -> dict[str, str]:
    """Serialize a Manifest into per-entity-type YAML files.

    Returns ``{filename: yaml_content}`` for non-empty entity types.
    Empty entity types are omitted (no file created).
    """
    data = manifest.model_dump(mode="json", exclude_defaults=True, by_alias=True)
    files: dict[str, str] = {}
    for key, filename in MANIFEST_FILES.items():
        section = data.get(key)
        if not section:
            continue
        files[filename] = yaml.dump(
            {key: section},
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
    return files


def parse_manifest_dir(files: dict[str, str]) -> Manifest:
    """Parse split YAML files into a single Manifest.

    ``files`` maps filename → YAML content (e.g. ``{"workflows.yaml": "..."}``).
    Missing files are treated as empty.
    """
    merged: dict[str, object] = {}
    for key, filename in MANIFEST_FILES.items():
        content = files.get(filename, "")
        if not content or not content.strip():
            continue
        data = yaml.safe_load(content)
        if data and isinstance(data, dict):
            merged[key] = data.get(key)
    return Manifest(**merged)  # type: ignore[arg-type]


def write_manifest_to_dir(manifest: Manifest, bifrost_dir: Path) -> None:
    """Write split manifest files to a directory. Removes legacy metadata.yaml."""
    bifrost_dir.mkdir(parents=True, exist_ok=True)

    files = serialize_manifest_dir(manifest)
    for filename, content in files.items():
        (bifrost_dir / filename).write_text(content)

    # Remove split files that are now empty (entity type was cleared)
    for filename in MANIFEST_FILES.values():
        if filename not in files:
            path = bifrost_dir / filename
            if path.exists():
                path.unlink()

    # Clean up legacy single-file manifest
    legacy = bifrost_dir / MANIFEST_LEGACY_FILE
    if legacy.exists():
        legacy.unlink()


def read_manifest_from_dir(bifrost_dir: Path) -> Manifest:
    """Read manifest from a directory, auto-detecting split vs legacy format.

    Detection: if any split file exists, use split format.
    Otherwise fall back to legacy metadata.yaml.
    Empty/missing directory returns empty Manifest.
    """
    if not bifrost_dir.exists():
        return Manifest()

    # Check for split files
    split_files: dict[str, str] = {}
    for filename in MANIFEST_FILES.values():
        path = bifrost_dir / filename
        if path.exists():
            split_files[filename] = path.read_text()

    if split_files:
        return parse_manifest_dir(split_files)

    # Fall back to legacy single file
    legacy = bifrost_dir / MANIFEST_LEGACY_FILE
    if legacy.exists():
        return parse_manifest(legacy.read_text())

    return Manifest()


# =============================================================================
# Validation
# =============================================================================


def validate_manifest(manifest: Manifest) -> list[str]:
    """
    Validate cross-references within the manifest.

    Checks:
    - All organization_id references point to declared organizations
    - All role references point to declared roles
    - Integration data_provider refs point to declared workflows
    - Config integration_id refs point to declared integrations
    - Table org/app refs point to declared entities
    - Event source webhook integration_id refs point to declared integrations
    - Event subscription workflow_id refs point to declared workflows

    Returns a list of human-readable error strings. Empty list = valid.
    """
    errors: list[str] = []

    org_ids = {org.id for org in manifest.organizations}
    role_ids = {role.id for role in manifest.roles}
    wf_ids = {wf.id for wf in manifest.workflows.values()}
    integration_ids = {integ.id for integ in manifest.integrations.values()}
    app_ids = {app.id for app in manifest.apps.values()}

    # Check organization references
    for name, wf in manifest.workflows.items():
        if wf.organization_id and wf.organization_id not in org_ids:
            errors.append(f"Workflow '{name}' references unknown organization: {wf.organization_id}")
        for role_id in wf.roles:
            if role_id not in role_ids:
                errors.append(f"Workflow '{name}' references unknown role: {role_id}")

    for name, form in manifest.forms.items():
        if form.organization_id and form.organization_id not in org_ids:
            errors.append(f"Form '{name}' references unknown organization: {form.organization_id}")
        for role_id in form.roles:
            if role_id not in role_ids:
                errors.append(f"Form '{name}' references unknown role: {role_id}")

    for name, agent in manifest.agents.items():
        if agent.organization_id and agent.organization_id not in org_ids:
            errors.append(f"Agent '{name}' references unknown organization: {agent.organization_id}")
        for role_id in agent.roles:
            if role_id not in role_ids:
                errors.append(f"Agent '{name}' references unknown role: {role_id}")

    for name, app in manifest.apps.items():
        if app.organization_id and app.organization_id not in org_ids:
            errors.append(f"App '{name}' references unknown organization: {app.organization_id}")
        for role_id in app.roles:
            if role_id not in role_ids:
                errors.append(f"App '{name}' references unknown role: {role_id}")

    # Integrations: data_provider must be a known workflow
    for name, integ in manifest.integrations.items():
        if integ.list_entities_data_provider_id and integ.list_entities_data_provider_id not in wf_ids:
            errors.append(
                f"Integration '{name}' references unknown data provider workflow: "
                f"{integ.list_entities_data_provider_id}"
            )
        for mapping in integ.mappings:
            if mapping.organization_id and mapping.organization_id not in org_ids:
                errors.append(
                    f"Integration '{name}' mapping references unknown organization: "
                    f"{mapping.organization_id}"
                )

    # Configs: integration_id and organization_id
    for key, cfg in manifest.configs.items():
        if cfg.integration_id and cfg.integration_id not in integration_ids:
            errors.append(f"Config '{key}' references unknown integration: {cfg.integration_id}")
        if cfg.organization_id and cfg.organization_id not in org_ids:
            errors.append(f"Config '{key}' references unknown organization: {cfg.organization_id}")

    # Tables: organization_id and application_id
    for name, table in manifest.tables.items():
        if table.organization_id and table.organization_id not in org_ids:
            errors.append(f"Table '{name}' references unknown organization: {table.organization_id}")
        if table.application_id and table.application_id not in app_ids:
            errors.append(f"Table '{name}' references unknown application: {table.application_id}")

    # Knowledge: role refs
    for ns_name, ns in manifest.knowledge.items():
        if ns.organization_id and ns.organization_id not in org_ids:
            errors.append(f"Knowledge namespace '{ns_name}' references unknown organization: {ns.organization_id}")
        for role_id in ns.roles:
            if role_id not in role_ids:
                errors.append(f"Knowledge namespace '{ns_name}' references unknown role: {role_id}")

    # Events: source + subscription refs
    for name, evt in manifest.events.items():
        if evt.organization_id and evt.organization_id not in org_ids:
            errors.append(f"Event source '{name}' references unknown organization: {evt.organization_id}")
        if evt.webhook_integration_id and evt.webhook_integration_id not in integration_ids:
            errors.append(
                f"Event source '{name}' references unknown webhook integration: "
                f"{evt.webhook_integration_id}"
            )
        for sub in evt.subscriptions:
            if sub.workflow_id not in wf_ids:
                errors.append(
                    f"Event source '{name}' subscription '{sub.id}' references unknown workflow: "
                    f"{sub.workflow_id}"
                )

    return errors


# =============================================================================
# Utilities
# =============================================================================


def get_all_entity_ids(manifest: Manifest) -> set[str]:
    """Get all entity UUIDs declared in the manifest."""
    ids: set[str] = set()
    for wf in manifest.workflows.values():
        ids.add(wf.id)
    for integ in manifest.integrations.values():
        ids.add(integ.id)
    for cfg in manifest.configs.values():
        ids.add(cfg.id)
    for table in manifest.tables.values():
        ids.add(table.id)
    for evt in manifest.events.values():
        ids.add(evt.id)
        for sub in evt.subscriptions:
            ids.add(sub.id)
    for form in manifest.forms.values():
        ids.add(form.id)
    for agent in manifest.agents.values():
        ids.add(agent.id)
    for app in manifest.apps.values():
        ids.add(app.id)
    return ids


def get_all_paths(manifest: Manifest) -> set[str]:
    """Get all file paths declared in the manifest."""
    paths: set[str] = set()
    for wf in manifest.workflows.values():
        paths.add(wf.path)
    for form in manifest.forms.values():
        paths.add(form.path)
    for agent in manifest.agents.values():
        paths.add(agent.path)
    for app in manifest.apps.values():
        paths.add(app.path)
    return paths
