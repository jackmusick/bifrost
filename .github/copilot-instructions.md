# Bifrost — Copilot Instructions

MSP automation platform: FastAPI backend + React frontend, with a git-synced workflow workspace. This repo has two distinct development contexts:

- **Platform development** (`bifrost/` subdir) — modifying Bifrost itself (API, client, workers, k8s)
- **Workflow workspace** (`workflows/`, `.bifrost/`) — building and deploying workflows to the Bifrost instance at `http://10.1.23.240`

---

## Commands

### Platform Development

```bash
# Start full dev stack with hot reload
./debug.sh

# Run all backend tests (always use this — never run pytest directly for e2e)
./test.sh

# Run a specific test file
./test.sh tests/e2e/platform/test_sdk_from_workflow.py

# Run a single test
./test.sh tests/e2e/platform/test_sdk_from_workflow.py::TestSDKFileOperations::test_file_path_sandboxing -v

# Run with coverage
./test.sh --coverage

# Run Playwright E2E tests
./test.sh --client

# Quality checks (run from respective directories)
cd api && pyright
cd api && ruff check .
cd client && npm run tsc
cd client && npm run lint

# Regenerate TypeScript types (requires dev stack running via ./debug.sh)
cd client && npm run generate:types
```

Test results are written as JUnit XML to `/tmp/bifrost/test-results.xml` — parse this for pass/fail details rather than grepping stdout.

### Workflow Workspace (syncing to 10.1.23.240)

```bash
# Fetch platform docs once per session (grep locally rather than re-fetching)
bifrost api GET /api/llms.txt > /tmp/bifrost-docs/llms.txt

# Start watch mode — auto-syncs all file changes to the platform
bifrost watch

# Run a workflow locally
bifrost run workflows/smoke/minio_put_list.py --workflow minio_put_list --params '{}'

# Execute a workflow on the platform
bifrost api POST /api/workflows/{id}/execute '{"workflow_id":"...","input_data":{},"sync":true}'

# Git-integrated deployment (do NOT use while bifrost watch is running)
bifrost git fetch        # regenerate manifest from DB, fetch remote
bifrost git commit -m "description"
bifrost git push         # pull + push + import entities

# Re-authenticate
bifrost login --url http://10.1.23.240
```

---

## Architecture

Everything runs in Docker. **Do not start uvicorn, vite, or pytest outside Docker.**

```
Client (React, :3000)  ──▶  FastAPI (:8000)  ──▶  PostgreSQL
                                  │
                         ┌────────┼────────┐
                         ▼        ▼        ▼
                       Redis  RabbitMQ   S3/MinIO
```

- **`http://localhost:3000`** is the single entry point — Vite proxies `/api/*` to the API
- **Hot reload is automatic** on all services — do not restart containers for code changes
- **`./debug.sh`** uses `docker-compose.dev.yml`; containers are prefixed `bifrost-dev-`

| When you need to... | Do this |
|---|---|
| New Python dependency | Add to `api/requirements.txt`, then `docker compose -f docker-compose.dev.yml up --build api` |
| Run a DB migration | `docker compose restart bifrost-init`, then restart `api` |
| Regenerate frontend types | `cd client && npm run generate:types` (stack must be running) |
| Check API logs | `docker compose -f docker-compose.dev.yml logs -f api` |

### File & Module Storage

| Content | Write path | Read path |
|---|---|---|
| All files | S3 `_repo/` via `RepoStorage` | S3 (source of truth) |
| Text files | + `file_index` DB | `file_index` for search only |
| Python workflows | + Redis via `set_module()` | Redis → S3 fallback |
| Compiled app files | S3 `_apps/{id}/preview/` | Redis render cache → S3 fallback |

**`get_module()` must NOT be used for non-Python files.** App source (TSX, YAML, etc.) always reads from S3 via `RepoStorage.read()`.

---

## Manifest & Git-Sync

`.bifrost/*.yaml` files round-trip all platform entities between the database and git. Key files:

| File | Purpose |
|---|---|
| `api/src/services/manifest.py` | Pydantic models (`ManifestWorkflow`, `ManifestIntegration`, etc.) |
| `api/src/services/manifest_generator.py` | DB → manifest (serialize) |
| `api/src/services/github_sync.py` | Manifest → DB (`_resolve_*` methods) + stale-entity cleanup |

### Non-destructive upsert pattern (critical)

`_resolve_integration` and related methods use **upsert-by-natural-key**, never delete-all + re-insert:
- `IntegrationConfigSchema` rows are FK-referenced by `Config` rows — deleting cascades to user data
- `IntegrationMapping` rows carry `oauth_token_id` set via OAuth flows — deleting loses this

### Adding a new manifest field

1. Add to the Pydantic model in `manifest.py`
2. Add serialization in `manifest_generator.py` (DB → YAML)
3. Add deserialization in `github_sync.py` `_resolve_*` method (YAML → DB) — include in **both** update-existing and insert-new paths
4. Write a round-trip unit test in `tests/unit/test_manifest.py` and an E2E test in `tests/e2e/platform/test_git_sync_local.py`

---

## Backend Conventions

- **Pydantic models** — all in `api/shared/models.py` (source of truth for types)
- **Business logic** — lives in `api/shared/`; handlers are thin HTTP wrappers only
- **Routing** — one handler file per base route (e.g., `/discovery` → `discovery_handlers.py`); sub-routes and helpers in the same file
- **Request/Response** — always use Pydantic request and response models
- **AsyncSession** — `expire_on_commit=False`, `autoflush=False`; if you need immediate DB visibility after a write (e.g., within the same request or test), call `await session.flush(); await session.commit()` explicitly

---

## Frontend Conventions

- **TypeScript types** are auto-generated from the OpenAPI spec — never write them manually
- Run `npm run generate:types` in `client/` after any API model change; output lands in `client/src/lib/v1.d.ts`
- **API service pattern** — create a service file in `client/src/services/` for each new endpoint group:

```typescript
import { apiClient } from "@/lib/api-client";
import type { components } from "@/lib/v1";

export type MyModel = components["schemas"]["MyModel"];

export async function getMyModels() {
  return apiClient.get<MyModel[]>("/api/my-models");
}
```

---

## Workflow Development (Workspace)

This repo uses **SDK-first** mode — `.bifrost/` directory exists, so local files are the source of truth.

### Before building

1. Fetch docs: `bifrost api GET /api/llms.txt > /tmp/bifrost-docs/llms.txt`
2. Start watch mode: `bifrost watch` (auto-syncs every file change)
3. Check which org to target: read `.bifrost/organizations.yaml`
4. Check available integrations: read `.bifrost/integrations.yaml`

### UUID generation (critical)

**Generate all entity UUIDs before writing any files.** Cross-references (workflow → form, agent → workflow) must be valid at write time.

```python
import uuid
wf_id = str(uuid.uuid4())
form_id = str(uuid.uuid4())
```

### Workflow file structure

```python
from bifrost import workflow
import logging

logger = logging.getLogger(__name__)

@workflow(category="CategoryName")
async def my_workflow(param: str):
    """One-line description becomes the workflow description."""
    logger.info(f"Running with {param}")
    return {"result": param}
```

Workflow files live in `workflows/category/name.py`. Register in `.bifrost/workflows.yaml`:

```yaml
<uuid>:
  id: <uuid>
  name: "Display Name"
  path: "workflows/category/name.py"
  function_name: "my_workflow"
  type: "workflow"
  category: "CategoryName"
  description: "One-line description"
  timeout_seconds: 1800
  access_level: "authenticated"
```

### Syncing rules

- `bifrost watch` handles all syncing — **do not run `bifrost push` or `bifrost git push` while watch is running**
- Use `bifrost git push` only for explicit git-integrated deployments
- MCP tools (`create_form`, `create_app`, `create_agent`, `create_event_source`) are for entities that can't be created from local files alone

### Dev server

- URL: `http://10.1.23.240`
- CLI installed via pipx
- Re-authenticate: `bifrost login --url http://10.1.23.240`
- MCP (for Claude Code): `claude mcp add --transport http bifrost http://10.1.23.240/mcp`

---

## Pre-Completion Checklist (platform changes)

Before marking any backend/frontend work done:

```bash
cd api && pyright && ruff check .
cd ../client && npm run generate:types && npm run tsc && npm run lint
cd .. && ./test.sh
```
