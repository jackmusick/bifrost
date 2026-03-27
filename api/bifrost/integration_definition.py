"""
Source-backed integration definition helpers.

This is a bridge layer for the fork's `.bifrost/` convergence work. It models a
portable integration definition file that can live in normal repo source, while
leaving runtime state (mappings, secrets, tokens, org-specific config) in the
database.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class SourceIntegrationConfigSchema(BaseModel):
    """Portable config schema item for a source-backed integration definition."""

    key: str = Field(description="Config key name")
    type: str = Field(description="string | int | bool | json | secret")
    required: bool = Field(default=False, description="Whether this config must be set")
    description: str | None = Field(default=None, description="Human-readable description")
    options: list[str] | None = Field(default=None, description="Allowed values for string config")
    position: int = Field(default=0, description="Display order in UI")


class SourceOAuthProvider(BaseModel):
    """Portable OAuth provider definition for a source-backed integration."""

    provider_name: str = Field(description="Provider identifier")
    display_name: str | None = Field(default=None, description="UI display name")
    oauth_flow_type: str = Field(default="authorization_code", description="OAuth flow type")
    client_id: str = Field(
        default="__NEEDS_SETUP__",
        description="OAuth client ID sentinel; never store a live secret-bearing client here",
    )
    authorization_url: str | None = Field(default=None, description="OAuth authorization endpoint")
    token_url: str | None = Field(default=None, description="OAuth token endpoint")
    token_url_defaults: dict | None = Field(default=None, description="Default params for token request")
    scopes: list[str] = Field(default_factory=list, description="OAuth scopes")
    redirect_uri: str | None = Field(default=None, description="OAuth redirect URI template")


class SourceIntegrationDefinition(BaseModel):
    """
    Portable integration definition.

    Deliberately excludes runtime state:
    - mappings
    - config values
    - OAuth tokens
    - org-specific overrides
    """

    id: str = Field(description="Integration UUID")
    name: str = Field(description="Display name")
    entity_id: str | None = Field(default=None, description="Field name for mapped entity identifier")
    entity_id_name: str | None = Field(default=None, description="Display label for the entity ID")
    list_entities_data_provider_id: str | None = Field(
        default=None,
        description="Workflow UUID for entity picker",
    )
    config_schema: list[SourceIntegrationConfigSchema] = Field(
        default_factory=list,
        description="Portable config schema",
    )
    oauth_provider: SourceOAuthProvider | None = Field(
        default=None,
        description="Portable OAuth provider definition",
    )

    def to_manifest_dict(self) -> dict:
        """
        Convert to the current manifest-shaped integration dict.

        This is an interim bridge for migration work. Runtime-only fields such
        as mappings are left empty.
        """

        data = self.model_dump(mode="python", exclude_none=True)
        data["mappings"] = []
        return data


def load_integration_definition(path: str | Path) -> SourceIntegrationDefinition:
    """Load one source-backed integration definition file."""

    definition_path = Path(path)
    data = yaml.safe_load(definition_path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{definition_path} did not contain a mapping")
    return SourceIntegrationDefinition(**data)


def discover_integration_definitions(root: str | Path) -> dict[str, SourceIntegrationDefinition]:
    """
    Discover `integrations/*/integration.yaml` files under a repo root.

    Returns a mapping keyed by slug directory name.
    """

    root_path = Path(root)
    definitions: dict[str, SourceIntegrationDefinition] = {}
    for path in sorted(root_path.glob("integrations/*/integration.yaml")):
        slug = path.parent.name
        definitions[slug] = load_integration_definition(path)
    return definitions
