"""Pydantic schemas for the platform model registry + admin migration flow."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlatformModelCapabilities(BaseModel):
    model_config = ConfigDict(extra="allow")

    supports_images_in: bool = False
    supports_images_out: bool = False
    supports_pdf_in: bool = False
    supports_tool_use: bool = False
    supports_audio_in: bool = False
    supports_audio_out: bool = False


class PlatformModelPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    model_id: str
    provider: str
    display_name: str
    cost_tier: str
    context_window: int | None = None
    max_output_tokens: int | None = None
    input_price_per_million: Decimal | None = None
    output_price_per_million: Decimal | None = None
    capabilities: PlatformModelCapabilities = Field(default_factory=PlatformModelCapabilities)
    deprecated_at: datetime | None = None
    is_active: bool


class PlatformModelListResponse(BaseModel):
    models: list[PlatformModelPublic]


class ModelMigrationByKind(BaseModel):
    organizations_default: int
    organizations_allowlist: int
    roles: int
    users: int
    workspaces: int
    conversations: int
    agents: int


class ModelMigrationImpactItem(BaseModel):
    model_id: str
    total: int
    by_kind: ModelMigrationByKind
    suggested_replacement: str | None = None


class ModelMigrationPreviewRequest(BaseModel):
    """List of model IDs the admin is about to lose access to."""

    old_model_ids: list[str] = Field(
        ...,
        min_length=1,
        description="The model IDs that will become unreachable after the change.",
    )


class ModelMigrationPreviewResponse(BaseModel):
    organization_id: UUID
    items: list[ModelMigrationImpactItem]
    total_references: int


class ModelMigrationApplyRequest(BaseModel):
    """Map of `old_model_id -> new_model_id_or_typed_string`.

    `new` may be a model_id from `platform_models`, an alias, or a free-typed
    string when the new provider's catalog isn't represented in
    `platform_models` yet (custom OpenAI-compatible endpoint, self-hosted, etc.).
    """

    replacements: dict[str, str] = Field(
        ...,
        min_length=1,
    )


class ModelMigrationApplyResponse(BaseModel):
    organization_id: UUID
    rewrites: dict[str, int]
    deprecations_added: int
