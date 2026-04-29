"""
Platform model registry — loader for `models.json`.

This module owns the schema of `api/shared/data/models.json` and provides:
- Pydantic types for the file's contents (`RegistryFile`, `RegistryModel`, etc.).
- Loaders for the bundled file (offline / first-boot seed) and for the remote
  GitHub-raw URL (kept fresh by a scheduled GitHub Action).

The registry is a CACHE in `platform_models` table; the sync job in
`api/src/jobs/schedulers/model_registry_sync.py` reads this loader's output and
upserts the table.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# Default URL points at the main branch of the Bifrost repo. Overridable via
# env var so self-hosters can point at a fork or private mirror.
DEFAULT_REGISTRY_URL = (
    "https://raw.githubusercontent.com/jackmusick/bifrost/main/api/shared/data/models.json"
)

BUNDLED_REGISTRY_PATH = Path(__file__).parent / "data" / "models.json"


class RegistryCapabilities(BaseModel):
    model_config = ConfigDict(extra="allow")

    supports_images_in: bool = False
    supports_images_out: bool = False
    supports_pdf_in: bool = False
    supports_tool_use: bool = False
    supports_audio_in: bool = False
    supports_audio_out: bool = False


class RegistryModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    provider: str
    display_name: str
    cost_tier: str
    context_window: int | None = None
    max_output_tokens: int | None = None
    input_price_per_million: Decimal | None = None
    output_price_per_million: Decimal | None = None
    capabilities: RegistryCapabilities = Field(default_factory=RegistryCapabilities)
    deprecated_at: datetime | None = None


class RegistryAlias(BaseModel):
    alias: str
    target_model_id: str
    display_name: str | None = None
    description: str | None = None


class RegistryDeprecation(BaseModel):
    old_model_id: str
    new_model_id: str
    deprecated_at: datetime
    notes: str | None = None


class RegistryFile(BaseModel):
    schema_version: int
    generated_at: datetime
    source: str | None = None
    models: list[RegistryModel]
    aliases: list[RegistryAlias] = Field(default_factory=list)
    deprecations: list[RegistryDeprecation] = Field(default_factory=list)


def load_bundled() -> RegistryFile:
    """Load the bundled `models.json` from disk. Used as the offline seed."""
    raw = BUNDLED_REGISTRY_PATH.read_text(encoding="utf-8")
    return RegistryFile.model_validate_json(raw)


def parse(raw: str | bytes | dict[str, Any]) -> RegistryFile:
    """Validate-and-parse a registry payload from JSON text or a dict."""
    if isinstance(raw, dict):
        return RegistryFile.model_validate(raw)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return RegistryFile.model_validate(json.loads(raw))
