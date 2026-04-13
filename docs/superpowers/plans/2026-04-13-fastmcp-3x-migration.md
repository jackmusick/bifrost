# FastMCP 2.x → 3.x Migration + python-jose Removal

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade fastmcp from 2.14.6 to 3.2.3+ to resolve CVE-2026-32871 (CVSS 10) and remove the unmaintained python-jose dependency.

**Architecture:** This is a dependency upgrade, not an architecture change. FastMCP 3.x preserved ~95% of the API surface Bifrost uses. The changes are: (1) update import paths from `fastmcp.tools.tool` to `fastmcp.tools`, (2) update the version pin, (3) update one error message referencing the old version, (4) remove python-jose from requirements. ToolResult constructor, Middleware, AccessToken, ToolError, dependencies, http_app(), add_tool(), and tool() all work identically in 3.x.

**Tech Stack:** Python 3.11, FastMCP 3.2.3+, PyJWT (already installed, replaces python-jose)

**Key reference:** FastMCP 3.x upgrade guide — constructor kwargs `json_response`/`stateless_http` moved from `FastMCP()` to `http_app()` (Bifrost already passes them to `http_app()`, so no change needed). Decorator `@mcp.tool()` now returns `FunctionTool` instead of original function (Bifrost doesn't use the return value). `ToolResult(content=str)` is auto-coerced to `list[ContentBlock]` via internal `_convert_to_content()`.

---

### Task 1: Update requirements.txt

**Files:**
- Modify: `requirements.txt:33-34` (python-jose removal — already done)
- Modify: `requirements.txt:117` (fastmcp version pin)

- [ ] **Step 1: Update fastmcp version pin**

In `requirements.txt`, change:
```
fastmcp>=2.0,<3  # FastMCP for MCP server (internal + external access)
```
to:
```
fastmcp>=3.2.0,<4  # FastMCP for MCP server (internal + external access)
```

- [ ] **Step 2: Verify python-jose is already removed**

Confirm `requirements.txt` no longer contains `python-jose`. (This was done in the earlier commit.)

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: bump fastmcp >=3.2.0 and drop python-jose"
```

---

### Task 2: Update ToolResult import paths (16 files)

The canonical 3.x import is `from fastmcp.tools import ToolResult` (not `from fastmcp.tools.tool import ToolResult`). The old path works via a compat shim but we want clean imports.

**Files:**
- Modify: `api/src/services/mcp_server/server.py:24`
- Modify: `api/src/services/mcp_server/tool_result.py:16`
- Modify: `api/src/services/mcp_server/generators/fastmcp_generator.py:12`

These are the only three files that import `ToolResult` directly. The 14 tool modules import from `tool_result.py`, not from fastmcp.

- [ ] **Step 1: Update server.py import**

In `api/src/services/mcp_server/server.py`, change line 24:
```python
from fastmcp.tools.tool import ToolResult
```
to:
```python
from fastmcp.tools import ToolResult
```

- [ ] **Step 2: Update tool_result.py import**

In `api/src/services/mcp_server/tool_result.py`, change line 16:
```python
from fastmcp.tools.tool import ToolResult
```
to:
```python
from fastmcp.tools import ToolResult
```

- [ ] **Step 3: Update fastmcp_generator.py import**

In `api/src/services/mcp_server/generators/fastmcp_generator.py`, change line 12:
```python
from fastmcp.tools.tool import ToolResult
```
to:
```python
from fastmcp.tools import ToolResult
```

- [ ] **Step 4: Commit**

```bash
git add api/src/services/mcp_server/server.py api/src/services/mcp_server/tool_result.py api/src/services/mcp_server/generators/fastmcp_generator.py
git commit -m "refactor: use canonical fastmcp 3.x import paths for ToolResult"
```

---

### Task 3: Update Tool base class import

**Files:**
- Modify: `api/src/services/mcp_server/server.py:510`

The `Tool` import for the `WorkflowTool` subclass. In 3.x, `from fastmcp.tools import Tool` is canonical.

- [ ] **Step 1: Update Tool import**

In `api/src/services/mcp_server/server.py`, change line 510:
```python
    from fastmcp.tools import Tool as _FastMCPTool  # type: ignore[import-not-found]
```
to:
```python
    from fastmcp.tools import Tool as _FastMCPTool
```

Remove the `type: ignore` — the import is valid in 3.x and pyright should resolve it.

- [ ] **Step 2: Commit**

```bash
git add api/src/services/mcp_server/server.py
git commit -m "refactor: update Tool import for fastmcp 3.x"
```

---

### Task 4: Update error message referencing old version

**Files:**
- Modify: `api/src/services/mcp_server/server.py:296-298`

- [ ] **Step 1: Update error message**

In `api/src/services/mcp_server/server.py`, change:
```python
        if not HAS_FASTMCP:
            raise ImportError(
                "fastmcp is required for MCP access. "
                "Install it with: pip install 'fastmcp>=2.0,<3'"
            )
```
to:
```python
        if not HAS_FASTMCP:
            raise ImportError(
                "fastmcp is required for MCP access. "
                "Install it with: pip install 'fastmcp>=3.2.0,<4'"
            )
```

- [ ] **Step 2: Commit**

```bash
git add api/src/services/mcp_server/server.py
git commit -m "chore: update fastmcp version in error message"
```

---

### Task 5: Rebuild container and run tests

The fastmcp upgrade is a new dependency version, so the container image needs rebuilding.

- [ ] **Step 1: Rebuild the API container**

```bash
docker compose -f docker-compose.dev.yml up --build api -d
```

Wait for the container to be healthy. Check that fastmcp 3.x installed:

```bash
docker exec bifrost-dev-api-1 pip show fastmcp | head -3
```

Expected: `Version: 3.2.3` (or later 3.2.x)

- [ ] **Step 2: Check API starts cleanly**

```bash
docker compose -f docker-compose.dev.yml logs --tail=30 api
```

Look for: no import errors, MCP server creation logs, no tracebacks.

- [ ] **Step 3: Run unit tests**

```bash
./test.sh tests/unit/
```

Parse `/tmp/bifrost/test-results.xml` for failures. All existing MCP tests should pass:
- `tests/unit/services/test_mcp_auth.py`
- `tests/unit/services/test_mcp_tools.py`
- `tests/unit/services/test_mcp_agent_scope.py`
- `tests/unit/services/test_mcp_utils.py`
- `tests/unit/test_mcp_tools_file_index.py`

- [ ] **Step 4: Run E2E tests**

```bash
./test.sh --e2e
```

- [ ] **Step 5: Run type checking and linting**

```bash
cd api && pyright && ruff check .
```

---

### Task 6: Manual smoke test (MCP endpoint)

- [ ] **Step 1: Verify MCP endpoint responds**

With dev stack running (`./debug.sh`):

```bash
curl -s http://localhost:3000/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
```

Should return a JSON-RPC response with server capabilities (or auth error if OAuth is enforced — either is fine, it means the MCP server is running).

- [ ] **Step 2: Commit final state (if any fixes were needed)**

If any adjustments were required during testing, commit them:

```bash
git add -A
git commit -m "fix: adjustments for fastmcp 3.x compatibility"
```

---

## Risk Notes

- **ToolResult constructor**: Verified that `ToolResult(content=str, structured_content=dict)` works in 3.x via auto-coercion. No changes needed to `tool_result.py`.
- **Middleware hooks**: `on_initialize`, `on_list_tools`, `on_call_tool` signatures unchanged. The generic type annotations on `MiddlewareContext` and `CallNext` are optional — the existing untyped signatures work fine.
- **`mcp.tool()` decorator**: Returns `FunctionTool` in 3.x instead of the original function. Bifrost uses the `mcp.tool(name=, description=)(wrapper)` pattern and discards the return value, so this is a no-op.
- **`WorkflowTool` subclass**: `Tool.run(self, arguments: dict) -> ToolResult` is unchanged. The `parameters` JSON Schema field and `model_config` are unchanged.
- **`http_app(json_response=True, stateless_http=True)`**: These kwargs moved FROM the `FastMCP()` constructor TO `http_app()` in 3.x. Bifrost already passes them to `http_app()`, so no change needed.
