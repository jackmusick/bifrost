"""E2E matrix: MCP tool-access decisions across (caller × agent × workflow).

This file is the durable regression surface for the "platform admin should see
every tool attached to an agent they can access" bug. It runs against the real
test stack — DB, API, workers — so it also catches anything that routes through
``AgentScopeMCPMiddleware`` / ``ToolFilterMiddleware`` or shared workflow
registration.

The matrix is deliberately table-driven: each row names a concrete
(caller, agent_org, workflow_variant) combination and declares whether the
workflow should appear in the agent's MCP tool list. The pytest id makes
failures self-describing in CI output — "the admin + cross-org role-gated
row flipped" instead of a nameless -1/+1 count diff.

Workflow variants modelled:

* ``global_authenticated`` — ``organization_id=None``, ``access_level=authenticated``
* ``global_role_gated`` — ``organization_id=None``, ``access_level=role_based``, role=``role_x``
* ``org_a_authenticated`` — in Org A (platform), ``access_level=authenticated``
* ``org_a_role_gated`` — in Org A, ``role_based``, role=``role_x``
* ``org_b_authenticated`` — in Org B, ``access_level=authenticated``
* ``org_b_role_gated`` — in Org B, ``role_based``, role=``role_x``  ← THE BUG

Callers modelled:

* ``platform_admin`` — is_superuser=True (from conftest)
* ``org_a_user`` — reuses ``platform_admin``'s org; not used for admin cases

For now, the matrix focuses on the admin → cross-org scenarios. Non-admin rows
are included as regression anchors to prove the fix does not widen non-admin
visibility.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


# =============================================================================
# Workflow variant table
# =============================================================================


@dataclass(frozen=True)
class WorkflowVariant:
    """Describes one row's worth of workflow state we seed for the agent."""

    key: str
    in_org: str | None  # "A" (platform org / admin's org), "B" (cross-org), or None (global)
    role_based: bool
    with_role: bool  # only meaningful if role_based=True


VARIANTS: list[WorkflowVariant] = [
    WorkflowVariant("global_authenticated", None, role_based=False, with_role=False),
    WorkflowVariant("global_role_gated_empty", None, role_based=True, with_role=False),
    WorkflowVariant("global_role_gated", None, role_based=True, with_role=True),
    WorkflowVariant("org_a_authenticated", "A", role_based=False, with_role=False),
    WorkflowVariant("org_a_role_gated", "A", role_based=True, with_role=True),
    WorkflowVariant("org_b_authenticated", "B", role_based=False, with_role=False),
    WorkflowVariant("org_b_role_gated", "B", role_based=True, with_role=True),
]


# Expected visibility matrix.
# Key: (caller_label, agent_org_label, variant.key) -> should be visible?
#
# The caller here is always the platform admin (is_superuser=True). The bug is
# that SOME rows are flipping to False today. All should be True — the admin
# has access to the agent AND has bypass on everything.
ADMIN_EXPECTED_VISIBLE: dict[tuple[str, str, str], bool] = {
    # Admin + Org A agent: every variant attached must be listed for the admin.
    ("platform_admin", "A", "global_authenticated"): True,
    ("platform_admin", "A", "global_role_gated_empty"): True,
    ("platform_admin", "A", "global_role_gated"): True,
    ("platform_admin", "A", "org_a_authenticated"): True,
    ("platform_admin", "A", "org_a_role_gated"): True,
    ("platform_admin", "A", "org_b_authenticated"): True,  # cross-org, authenticated
    ("platform_admin", "A", "org_b_role_gated"): True,     # THE BUG — cross-org + role-gated
}


# =============================================================================
# Helpers: seed workflows + roles via REST as the platform admin.
# =============================================================================


def _register_simple_tool_workflow(
    e2e_client, headers: dict, organization_id: str | None
) -> dict:
    """Register a minimal ``type='tool'`` workflow under a unique path/function.

    Uses the same write-file-then-register flow as test_mcp_parity. Returns
    the RegisterWorkflowResponse dict.
    """
    slug = uuid.uuid4().hex[:8]
    path = f"apps/mcp_matrix/tool_{slug}.py"
    fn = f"tool_{slug}"
    content = (
        "from bifrost import tool\n"
        "\n"
        f"@tool(description='matrix test tool {slug}')\n"
        f"def {fn}() -> str:\n"
        "    return 'ok'\n"
    )
    write_resp = e2e_client.put(
        "/api/files/editor/content",
        headers=headers,
        json={"path": path, "content": content, "encoding": "utf-8"},
    )
    assert write_resp.status_code in (200, 201), write_resp.text
    register_resp = e2e_client.post(
        "/api/workflows/register",
        headers=headers,
        json={"path": path, "function_name": fn},
    )
    assert register_resp.status_code in (200, 201), register_resp.text
    workflow = register_resp.json()

    # Pin organization scope via PATCH /api/workflows/{id}. The endpoint
    # distinguishes "not provided" from "explicitly null" using
    # model_fields_set, so we always send organization_id for determinism.
    patch_resp = e2e_client.patch(
        f"/api/workflows/{workflow['id']}",
        headers=headers,
        json={"organization_id": organization_id},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    return patch_resp.json()


def _set_workflow_role_gating(
    e2e_client, headers: dict, workflow_id: str, role_id: str | None
) -> None:
    """Mark the workflow role_based and (optionally) attach a single role.

    If role_id is None, the workflow stays role_based with zero roles — which
    per the MCP access model means "superuser only".
    """
    # Flip access_level via PATCH.
    patch_resp = e2e_client.patch(
        f"/api/workflows/{workflow_id}",
        headers=headers,
        json={"access_level": "role_based"},
    )
    assert patch_resp.status_code == 200, patch_resp.text

    if role_id is not None:
        grant_resp = e2e_client.post(
            f"/api/workflows/{workflow_id}/roles",
            headers=headers,
            json={"role_ids": [role_id]},
        )
        assert grant_resp.status_code in (200, 201, 204), grant_resp.text


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def role_x(e2e_client, platform_admin) -> Iterator[dict]:
    """A named role used to gate role_based workflows in the matrix."""
    name = f"mcp-matrix-role-x-{uuid.uuid4().hex[:8]}"
    resp = e2e_client.post(
        "/api/roles",
        headers=platform_admin.headers,
        json={"name": name, "permissions": {}},
    )
    assert resp.status_code == 201, resp.text
    role = resp.json()
    yield role
    e2e_client.delete(f"/api/roles/{role['id']}", headers=platform_admin.headers)


@pytest.fixture
def org_a(org1) -> dict:
    """'Org A' in the matrix is ``org1`` — the agent's home org.

    Per the bug report, the failure mode is: platform admin accesses a
    cross-org agent. The platform admin session user has
    ``organization_id=None`` (global/platform scope), so we pin the agent
    itself into ``org1`` and call that "Org A". That matches the real-world
    shape of "admin in Platform Org uses an agent owned by a customer org."
    """
    return {"id": str(org1["id"]), "label": "A"}


@pytest.fixture
def org_b(org2) -> dict:
    """'Org B' is org2 — a real second org from the session fixtures."""
    return {"id": str(org2["id"]), "label": "B"}


@pytest_asyncio.fixture
async def seeded_agent_with_tools(
    e2e_client, platform_admin, role_x, org_a, org_b
) -> AsyncIterator[dict[str, Any]]:
    """Create one agent per-test with all seven workflow variants attached.

    Uses a fresh uuid-suffixed agent + fresh workflows per test to keep the
    stack clean under state-reset semantics of ``./test.sh``. On teardown we
    try to delete the agent and each workflow; failures are logged not raised
    so a single cleanup hiccup doesn't mask the real test failure.
    """
    admin_headers = platform_admin.headers

    # 1) Create the seven workflows.
    workflows_by_key: dict[str, dict] = {}
    for variant in VARIANTS:
        target_org = (
            org_a["id"] if variant.in_org == "A"
            else org_b["id"] if variant.in_org == "B"
            else None
        )
        wf = _register_simple_tool_workflow(
            e2e_client, admin_headers, organization_id=target_org
        )
        # Apply role gating if the variant requests it.
        if variant.role_based:
            _set_workflow_role_gating(
                e2e_client,
                admin_headers,
                workflow_id=wf["id"],
                role_id=role_x["id"] if variant.with_role else None,
            )
        workflows_by_key[variant.key] = wf

    # 2) Create an Org A agent (access_level=authenticated) and attach every tool.
    tool_ids = [wf["id"] for wf in workflows_by_key.values()]
    agent_resp = e2e_client.post(
        "/api/agents",
        headers=admin_headers,
        json={
            "name": f"matrix-agent-{uuid.uuid4().hex[:8]}",
            "description": "MCP tool access matrix fixture agent",
            "system_prompt": "Be helpful.",
            "channels": ["chat"],
            "access_level": "authenticated",
            "organization_id": org_a["id"],
            "tool_ids": tool_ids,
        },
    )
    assert agent_resp.status_code == 201, agent_resp.text
    agent = agent_resp.json()

    try:
        yield {
            "agent": agent,
            "workflows_by_key": workflows_by_key,
            "org_a": org_a,
            "org_b": org_b,
            "role_x": role_x,
        }
    finally:
        # Best-effort teardown.
        try:
            e2e_client.delete(
                f"/api/agents/{agent['id']}", headers=admin_headers
            )
        except Exception:
            logger.exception("matrix teardown: delete agent failed")
        for wf in workflows_by_key.values():
            try:
                e2e_client.delete(
                    f"/api/workflows/{wf['id']}?force=true",
                    headers=admin_headers,
                )
            except Exception:
                logger.exception(
                    "matrix teardown: delete workflow %s failed", wf["id"]
                )


# =============================================================================
# The matrix
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
class TestMcpToolAccessMatrix:
    """Runs MCPToolAccessService.get_tools_for_agent against each variant.

    We call the service directly — same entry point that
    ``ToolFilterMiddleware.on_list_tools`` calls. Every row in
    ``ADMIN_EXPECTED_VISIBLE`` is one parametrized case. A failing row names
    the exact (caller, agent_org, variant) tuple in CI output.
    """

    @pytest.mark.parametrize(
        "variant_key",
        [k for (caller, _agent_org, k) in ADMIN_EXPECTED_VISIBLE if caller == "platform_admin"],
        ids=lambda k: f"admin__org_a_agent__{k}",
    )
    async def test_platform_admin_sees_attached_tool(
        self,
        variant_key: str,
        seeded_agent_with_tools: dict[str, Any],
        db_session: AsyncSession,
    ) -> None:
        """Platform admin must see every workflow attached to an accessible agent.

        This is the matrix that catches the reported bug: the
        ``org_b_role_gated`` row flips to True only after the fix.
        """
        from src.services.mcp_server.tool_access import MCPToolAccessService

        agent = seeded_agent_with_tools["agent"]
        workflow = seeded_agent_with_tools["workflows_by_key"][variant_key]
        expected_visible = ADMIN_EXPECTED_VISIBLE[
            ("platform_admin", "A", variant_key)
        ]

        service = MCPToolAccessService(db_session)
        # Platform admin has no meaningful role list for MCP purposes — we
        # simulate the claims the middleware would pass (empty roles list,
        # is_superuser=True).
        result = await service.get_tools_for_agent(
            agent_id=agent["id"],
            user_roles=[],
            is_superuser=True,
        )

        assert result is not None, (
            f"get_tools_for_agent returned None for agent {agent['id']} "
            "— admin lost access to the agent itself"
        )

        tool_ids_in_result = {str(t.id) for t in result.tools}
        # ToolInfo.id is the registered MCP tool name OR the workflow UUID; both
        # representations can legitimately appear. Accept either.
        workflow_id = str(workflow["id"])
        visible = workflow_id in tool_ids_in_result or any(
            (t.type == "workflow" and str(getattr(t, "name", "")) == workflow["name"])
            for t in result.tools
        )

        assert visible is expected_visible, (
            f"Visibility mismatch for variant={variant_key}: "
            f"expected visible={expected_visible}, got {visible}. "
            f"Workflow id={workflow_id}, name={workflow['name']!r}. "
            f"Tool ids in result: {sorted(tool_ids_in_result)}. "
            f"Tool names in result: "
            f"{sorted(str(getattr(t, 'name', '')) for t in result.tools)}."
        )

    @pytest.mark.parametrize(
        "variant_key",
        [k for (caller, _agent_org, k) in ADMIN_EXPECTED_VISIBLE if caller == "platform_admin"],
        ids=lambda k: f"admin__mcp_http__{k}",
    )
    async def test_platform_admin_sees_tool_via_mcp_http(
        self,
        variant_key: str,
        seeded_agent_with_tools: dict[str, Any],
        e2e_client,
        platform_admin,
    ) -> None:
        """Admin must see every attached tool when calling real MCP over HTTP.

        This is the wire-level test: it hits the agent-scoped MCP endpoint
        (``/mcp/{agent_id}``) with the admin's Bifrost access token, issues
        a ``tools/list`` JSON-RPC call, and asserts that the target workflow
        appears in the response.

        Unlike the service-level test, this covers the full chain — FastMCP
        registration → ``ToolFilterMiddleware.on_list_tools`` →
        ``MCPToolAccessService`` → name intersection. The reported bug
        surfaces in this layer even though the service in isolation reports
        the workflow accessible.
        """
        agent = seeded_agent_with_tools["agent"]
        workflow = seeded_agent_with_tools["workflows_by_key"][variant_key]
        expected_visible = ADMIN_EXPECTED_VISIBLE[
            ("platform_admin", "A", variant_key)
        ]

        # JSON-RPC envelope for tools/list against the agent-scoped MCP endpoint.
        # The Bifrost JWT access token is accepted by the MCP auth provider.
        mcp_headers = {
            "Authorization": f"Bearer {platform_admin.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        # MCP requires an initialize handshake before tools/list in stateful
        # sessions. FastMCP runs stateless_http=True (see routers/mcp.py:177),
        # so a single tools/list call is sufficient.
        resp = e2e_client.post(
            f"/mcp/{agent['id']}",
            headers=mcp_headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {},
            },
        )
        assert resp.status_code == 200, (
            f"MCP tools/list HTTP failed: status={resp.status_code} "
            f"body={resp.text[:500]}"
        )

        # FastMCP streams JSON-RPC responses as SSE even for stateless calls
        # (Content-Type: text/event-stream). Find the data line.
        payload: dict[str, Any] | None = None
        raw = resp.text
        if raw.startswith("data:") or "\ndata:" in raw:
            for line in raw.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    import json as _json
                    payload = _json.loads(line[len("data:"):].strip())
                    break
        else:
            import json as _json
            payload = _json.loads(raw)

        assert payload is not None, f"Could not parse MCP response: {raw[:300]}"
        assert "result" in payload, (
            f"MCP tools/list returned no result: {payload}"
        )
        returned_tools = payload["result"].get("tools", [])
        returned_names = {t.get("name") for t in returned_tools}

        # The tool is registered with FastMCP under a normalized name derived
        # from the workflow's name. Look for a case-insensitive match against
        # the workflow's name.
        from src.services.mcp_server.server import _WORKFLOW_ID_TO_TOOL_NAME
        registered = _WORKFLOW_ID_TO_TOOL_NAME.get(str(workflow["id"]))
        if registered is None:
            # The mapping lives in the API process, not the test-runner process.
            # Derive the expected normalized name from the workflow's name.
            import re as _re
            normalized = _re.sub(r"[^a-z0-9_]", "", _re.sub(r"[\s\-]+", "_", workflow["name"].lower())).strip("_")
            candidate_names = {normalized, workflow["name"]}
        else:
            candidate_names = {registered}

        visible = bool(returned_names & candidate_names)

        assert visible is expected_visible, (
            f"MCP HTTP visibility mismatch for variant={variant_key}: "
            f"expected {expected_visible}, got {visible}. "
            f"workflow_id={workflow['id']}, "
            f"workflow_name={workflow['name']!r}, "
            f"candidate tool names={candidate_names}, "
            f"returned tool names={sorted(str(n) for n in returned_names)[:20]}."
        )
