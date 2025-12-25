# SDK Simplification Plan

## Problem Summary

The Bifrost SDK has significant complexity stemming from dual-mode operation that causes fragility and constant re-testing:

**Current Pain:** Every method has branching logic like:
```python
if _is_platform_context():
    # Redis/direct DB path - imports from src.core.cache, ._internal, ._write_buffer
else:
    # API call path - uses client.py
```

**Root Issues:**
- **7 duplicated dataclasses** across `bifrost/*.py` mirroring `src/models/contracts/*.py`
- **~300 lines of string-based code generation** in `cli.py`
- **Identical helper functions** copied across 6+ modules
- **Two `_context.py` implementations** (platform vs external)

## Design Decision

**API-Only Architecture:** Platform workflows also call API endpoints, just like external CLI.

This eliminates dual-mode entirely. The workflow engine injects an authenticated HTTP client.

## Architecture

### What Changes

**Engine (stays complex):** Manages workflow execution, context setup, result handling.
- Location: `api/src/sdk/context.py`, `api/src/jobs/execute_workflow.py`
- No changes needed - this complexity is inherent to execution management.

**SDK (gets simplified):** What workflow code imports (`from bifrost import organizations`).
- Location: `api/bifrost/*.py`
- Currently has dual-mode branching. We unify to HTTP-only.

### Before (Current)
```
Platform Workflow → SDK → Redis Cache + Write Buffer → Flushed to DB
External CLI      → SDK → HTTP API → PostgreSQL
```

### After (Simplified)
```
Platform Workflow → SDK → HTTP API (localhost) → PostgreSQL
External CLI      → SDK → HTTP API             → PostgreSQL
```

**Key insight:** The SDK becomes a thin HTTP wrapper. All the "smart" logic (permissions, caching, transactions) moves to API handlers where it belongs.

---

## Task 1: Fix Blocking I/O in CLI Endpoints

**Purpose:** Prerequisite before SDK simplification - CLI endpoints will be called much more frequently.

### HIGH Priority

| File | Line | Issue | Fix |
|------|------|-------|-----|
| `src/routers/cli.py` | 298 | `open()` file read | Use `aiofiles.open()` |
| `src/routers/cli.py` | 321 | `open()` file write | Use `aiofiles.open()` |
| `src/routers/cli.py` | 384 | `shutil.rmtree()` | Use `asyncio.to_thread()` |
| `src/routers/cli.py` | 1932-1942 | Sync tarball generation | Move to thread pool |

### MEDIUM Priority

| File | Line | Issue | Fix |
|------|------|-------|-----|
| `src/routers/cli.py` | 488 | `encrypt_secret()` sync | Use `asyncio.to_thread()` |
| `src/routers/cli.py` | 733,745,752 | Multiple `decrypt_secret()` calls | Batch in thread pool |
| `src/routers/integrations.py` | 1392 | `write_text()` sync | Use `aiofiles` |
| `src/routers/maintenance.py` | 68,78 | `rglob()` + `read_text()` | Use async alternatives |

### Fix Patterns
```python
# For CPU-bound (crypto):
result = await asyncio.to_thread(encrypt_secret, value)

# For file I/O:
import aiofiles
async with aiofiles.open(path, 'r') as f:
    content = await f.read()
```

---

## Task 2: Create Shared Models Package

**File:** `api/bifrost/models.py`

Create Pydantic models that serve as single source of truth for SDK types.

### Models to Create

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Any

class Organization(BaseModel):
    id: str
    name: str
    domain: str | None = None
    is_active: bool = True
    created_by: str = "system"
    created_at: datetime | None = None
    updated_at: datetime | None = None

class Role(BaseModel):
    id: str
    name: str
    description: str | None = None
    organization_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

class UserPublic(BaseModel):
    id: str
    email: str
    name: str
    is_active: bool
    is_superuser: bool
    is_verified: bool
    is_registered: bool
    user_type: str
    organization_id: str | None
    mfa_enabled: bool
    created_at: datetime | None
    updated_at: datetime | None

class FormPublic(BaseModel):
    id: str
    name: str
    description: str | None
    workflow_id: str | None
    launch_workflow_id: str | None
    default_launch_params: dict | None
    allowed_query_params: list[str] | None
    form_schema: dict | None
    access_level: str
    organization_id: str | None
    is_active: bool
    file_path: str | None
    created_at: datetime | None
    updated_at: datetime | None

class WorkflowMetadata(BaseModel):
    id: str
    name: str
    description: str | None
    category: str | None
    tags: list[str]
    parameters: dict
    execution_mode: str
    timeout_seconds: int | None
    retry_policy: dict | None
    schedule: str | None
    endpoint_enabled: bool
    allowed_methods: list[str] | None
    disable_global_key: bool
    public_endpoint: bool
    is_tool: bool
    tool_description: str | None
    time_saved: int | None
    source_file_path: str | None
    relative_file_path: str | None

class WorkflowExecution(BaseModel):
    execution_id: str
    workflow_name: str
    org_id: str | None
    form_id: str | None
    executed_by: str | None
    executed_by_name: str | None
    status: str
    input_data: dict | None
    result: Any
    result_type: str | None
    error_message: str | None
    duration_ms: int | None
    started_at: datetime | None
    completed_at: datetime | None
    logs: list[dict] | None
    variables: dict | None
    session_id: str | None
    peak_memory_bytes: int | None
    cpu_total_seconds: float | None

class IntegrationData(BaseModel):
    integration_id: str
    entity_id: str | None
    entity_name: str | None
    config: dict
    oauth: "OAuthCredentials | None" = None

class OAuthCredentials(BaseModel):
    connection_name: str
    client_id: str | None
    client_secret: str | None
    authorization_url: str | None
    token_url: str | None
    scopes: list[str]
    access_token: str | None
    refresh_token: str | None
    expires_at: str | None

class IntegrationMappingResponse(BaseModel):
    id: str
    integration_id: str
    organization_id: str
    entity_id: str
    entity_name: str | None
    oauth_token_id: str | None
    config: dict
    created_at: datetime
    updated_at: datetime

class ConfigData(BaseModel):
    """Dict-like config with attribute access."""
    data: dict[str, Any]

    def __getattr__(self, key: str) -> Any:
        return self.data.get(key)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

class AIResponse(BaseModel):
    content: str
    input_tokens: int
    output_tokens: int
    model: str

class AIStreamChunk(BaseModel):
    content: str
    done: bool
    input_tokens: int | None = None
    output_tokens: int | None = None

class KnowledgeDocument(BaseModel):
    id: str
    namespace: str
    content: str
    metadata: dict | None
    score: float | None
    organization_id: str | None
    key: str | None
    created_at: datetime | None

class NamespaceInfo(BaseModel):
    namespace: str
    scopes: dict  # global/org/total counts
```

---

## Task 3: Simplify SDK Modules (API-Only)

Rewrite each module to be API-only. Order by dependency (start with no-dependency modules).

### Rewrite Order

1. `config.py` - No dependencies
2. `files.py` - No dependencies
3. `knowledge.py` - No dependencies
4. `ai.py` - No dependencies
5. `integrations.py` - No dependencies
6. `organizations.py` - No dependencies
7. `users.py` - No dependencies
8. `roles.py` - Depends on users
9. `forms.py` - No dependencies
10. `executions.py` - No dependencies
11. `workflows.py` - Depends on executions

### Template for Each Module

```python
"""
bifrost/{module}.py - API-only implementation
"""
from typing import Any
from .models import ModelName
from ._client import get_client


class ModuleName:
    """SDK module for {feature}."""

    @staticmethod
    async def get(item_id: str) -> ModelName:
        """Get item by ID."""
        client = get_client()
        response = await client.get(f"/api/{endpoint}/{item_id}")
        response.raise_for_status()
        return ModelName.model_validate(response.json())

    @staticmethod
    async def list(**filters) -> list[ModelName]:
        """List items with optional filters."""
        client = get_client()
        response = await client.get("/api/{endpoint}", params=filters)
        response.raise_for_status()
        return [ModelName.model_validate(item) for item in response.json()]

    # ... other methods
```

### Module-Specific Notes

**`ai.py`** - Streaming must parse SSE format:
```python
async def stream(...) -> AsyncGenerator[AIStreamChunk, None]:
    client = get_client()
    async with client.stream("POST", "/api/cli/ai/stream", json=payload) as response:
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if data == "[DONE]":
                    break
                yield AIStreamChunk.model_validate(data)
```

**`files.py`** - Location handling stays same, just uses API:
```python
async def read(path: str, location: str = "workspace") -> str:
    client = get_client()
    response = await client.post("/api/cli/files/read", json={"path": path, "location": location})
    response.raise_for_status()
    return response.json()["content"]
```

---

## Task 4: Update Client Module

**File:** `api/bifrost/client.py`

Add client injection for platform mode.

```python
"""
bifrost/client.py - HTTP client with injection support
"""
import os
import httpx
from pathlib import Path
from typing import Optional

_injected_client: Optional["BifrostClient"] = None


class BifrostClient:
    """HTTP client for Bifrost API."""

    def __init__(self, api_url: str, access_token: str):
        self.api_url = api_url.rstrip("/")
        self.access_token = access_token
        self._client = httpx.AsyncClient(
            base_url=self.api_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )

    async def get(self, path: str, **kwargs) -> httpx.Response:
        return await self._client.get(path, **kwargs)

    async def post(self, path: str, **kwargs) -> httpx.Response:
        return await self._client.post(path, **kwargs)

    async def put(self, path: str, **kwargs) -> httpx.Response:
        return await self._client.put(path, **kwargs)

    async def patch(self, path: str, **kwargs) -> httpx.Response:
        return await self._client.patch(path, **kwargs)

    async def delete(self, path: str, **kwargs) -> httpx.Response:
        return await self._client.delete(path, **kwargs)

    def stream(self, method: str, path: str, **kwargs):
        return self._client.stream(method, path, **kwargs)

    async def close(self):
        await self._client.aclose()


def _set_client(client: BifrostClient) -> None:
    """Inject client for platform mode. Called by workflow engine."""
    global _injected_client
    _injected_client = client


def _clear_client() -> None:
    """Clear injected client after workflow execution."""
    global _injected_client
    _injected_client = None


def get_client() -> BifrostClient:
    """Get the active client (injected or from credentials)."""
    global _injected_client

    # Platform mode: use injected client
    if _injected_client is not None:
        return _injected_client

    # External mode: load from credentials file
    creds = _load_credentials()
    if creds:
        return BifrostClient(creds["api_url"], creds["access_token"])

    raise RuntimeError("Not logged in. Run 'bifrost login' to authenticate.")


def _load_credentials() -> Optional[dict]:
    """Load credentials from ~/.bifrost/credentials.json."""
    creds_file = Path.home() / ".bifrost" / "credentials.json"
    if creds_file.exists():
        import json
        return json.loads(creds_file.read_text())
    return None
```

---

## Task 5: Update Workflow Engine

**File:** `api/src/jobs/execute_workflow.py`

Inject authenticated client before running workflow code.

```python
import os
import bifrost
from bifrost.client import BifrostClient, _set_client, _clear_client

async def execute_workflow(...):
    # Create execution token with context
    token = create_execution_token(
        execution_id=execution_id,
        user_id=user_id,
        org_id=org_id,
    )

    # Get API URL (docker internal or external)
    api_url = os.getenv("BIFROST_API_URL", "http://api:8000")

    # Inject client for SDK calls
    client = BifrostClient(api_url=api_url, access_token=token)
    _set_client(client)

    try:
        # Run workflow code (SDK calls now go through API)
        result = await run_workflow(...)
    finally:
        # Clean up
        _clear_client()
        await client.close()
```

**Also update:** `docker-compose.yml`, `docker-compose.dev.yml`
```yaml
services:
  worker:
    environment:
      - BIFROST_API_URL=http://api:8000
  scheduler:
    environment:
      - BIFROST_API_URL=http://api:8000
```

---

## Task 6: Simplify CLI Download

**File:** `api/src/routers/cli.py`

Remove code generation, just package actual files.

### Remove These Functions (~300 lines)
- `_add_generated_files_to_tarball()`
- `_get_decorators_py()`
- `_get_cli_runner_py()`
- `_get_models_py()`

### New Download Endpoint
```python
@router.get("/download")
async def download_cli():
    """Download Bifrost SDK package."""
    buffer = io.BytesIO()

    # Package actual bifrost/ directory
    package_dir = Path(__file__).parent.parent.parent / "bifrost"

    async def generate_tarball():
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for file_path in package_dir.rglob("*"):
                if file_path.is_file() and not file_path.name.startswith("_"):
                    arcname = f"bifrost/{file_path.relative_to(package_dir)}"
                    tar.add(file_path, arcname=arcname)

    await asyncio.to_thread(generate_tarball)

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/gzip",
        headers={"Content-Disposition": "attachment; filename=bifrost.tar.gz"}
    )
```

---

## Task 7: Delete Obsolete Files

After all modules are converted:

| File | Reason |
|------|--------|
| `api/bifrost/_internal.py` | Permissions now validated by API |
| `api/bifrost/_write_buffer.py` | Writes go through API |
| `api/bifrost/_sync.py` | Platform-only sync logic |
| `api/bifrost/_logging.py` | Platform-only logging |

---

## Task 8: Update __init__.py Exports

**File:** `api/bifrost/__init__.py`

Clean up exports to use new models.

```python
"""
Bifrost SDK - API-only implementation
"""
from .models import (
    Organization,
    Role,
    UserPublic,
    FormPublic,
    WorkflowMetadata,
    WorkflowExecution,
    IntegrationData,
    OAuthCredentials,
    IntegrationMappingResponse,
    ConfigData,
    AIResponse,
    AIStreamChunk,
    KnowledgeDocument,
    NamespaceInfo,
)

from .organizations import organizations
from .roles import roles
from .users import users
from .forms import forms
from .workflows import workflows
from .executions import executions
from .config import config
from .integrations import integrations
from .files import files
from .ai import ai
from .knowledge import knowledge

# Re-export decorators from engine (unchanged)
from src.sdk.decorators import workflow, data_provider
from src.sdk.context import context, ExecutionContext

__all__ = [
    # Modules
    "organizations",
    "roles",
    "users",
    "forms",
    "workflows",
    "executions",
    "config",
    "integrations",
    "files",
    "ai",
    "knowledge",
    # Models
    "Organization",
    "Role",
    "UserPublic",
    "FormPublic",
    "WorkflowMetadata",
    "WorkflowExecution",
    "IntegrationData",
    "OAuthCredentials",
    "IntegrationMappingResponse",
    "ConfigData",
    "AIResponse",
    "AIStreamChunk",
    "KnowledgeDocument",
    "NamespaceInfo",
    # Decorators
    "workflow",
    "data_provider",
    # Context
    "context",
    "ExecutionContext",
]
```

---

## CLI Endpoints Reference (Must Preserve)

All these endpoints already exist and must work correctly:

| Module | Endpoints | Status |
|--------|-----------|--------|
| integrations | `/api/cli/integrations/*` | ✅ Exists |
| ai | `/api/cli/ai/*` | ✅ Exists |
| knowledge | `/api/cli/knowledge/*` | ✅ Exists |
| config | `/api/cli/config/*` | ✅ Exists |
| files | `/api/cli/files/*` | ✅ Exists |
| sessions | `/api/cli/sessions/*` | ✅ Exists |
| context | `/api/cli/context` | ✅ Exists |
| users | `/api/users/*` | ✅ Exists |
| organizations | `/api/organizations/*` | ✅ Exists |
| roles | `/api/roles/*` | ✅ Exists |
| forms | `/api/forms/*` | ✅ Exists |
| executions | `/api/executions/*` | ✅ Exists |
| workflows | `/api/workflows/*` | ✅ Exists |

---

## Benefits Summary

1. **Single code path** - No more `if _is_platform_context()` branching
2. **One source of truth** - Pydantic models in `models.py`
3. **~60% code reduction** - Each module shrinks from ~400 to ~100 lines
4. **No code generation** - CLI download is trivial tarball
5. **Simpler testing** - Test API endpoints, SDK is thin wrapper
6. **Server-side security** - All permissions validated on API
