"""Mechanical enforcement of the org-scoping pattern.

Three tests:

1. ``test_no_inline_org_scoping_in_routers`` — no raw ``organization_id ==``
   or ``organization_id.is_(None)`` outside the canonical
   ``OrgScopedRepository`` base class. Allow-listed lines are exempt with a
   one-line justification.

2. ``test_org_scoped_models_have_repository`` — every ORM model with an
   ``organization_id`` column either has an ``OrgScopedRepository``
   subclass or is on the explicit identity-entity allow-list.

3. ``test_sdk_endpoints_use_resolver`` — every SDK endpoint that accepts a
   ``scope`` parameter calls ``resolve_effective_scope``. Allow-listed
   endpoints document why they're exempt.

These tests are the load-bearing mechanism that prevents the pattern from
drifting. Allow-lists shrink as code migrates. When you add an entry,
include a comment explaining why — code review enforces accountability.

See ``api/src/repositories/README.md`` for the full pattern.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

API_ROOT = Path(__file__).resolve().parents[2] / "src"
ROUTERS_DIR = API_ROOT / "routers"
MODELS_ORM_DIR = API_ROOT / "models" / "orm"
REPOSITORIES_DIR = API_ROOT / "repositories"


# ---------------------------------------------------------------------------
# Test 1: No inline org scoping in routers
# ---------------------------------------------------------------------------

# Pattern: "<something>.organization_id == ..." or
# "<something>.organization_id.is_(None)" or
# "<something>.organization_id.in_(...)".
#
# We match the operator forms used in SQLAlchemy expressions. Comments and
# string literals are NOT excluded by the regex — we lean on the allow-list
# to handle those. (A python-ast-aware approach would be cleaner but the
# allow-list approach keeps the test cheap and the violation set visible.)
_INLINE_ORG_RE = re.compile(
    r"\b\w+\.organization_id\s*(?:==|\.is_\s*\(|\.in_\s*\()"
)

# Lines that are exempt from the no-inline rule. Each entry is
# (file_relative_to_api_root, line_number, reason).
#
# The goal of phases 4-7 is to SHRINK this list. Adding a new entry should
# be rare and obvious in code review.
ALLOW_LIST_INLINE_ORG: set[tuple[str, int, str]] = {
    # --- Repository classes that happen to live in routers/ ---
    # Phase 6 relocates these to repositories/. While they're here, the
    # cascade primitives inside their overridden methods are legal because
    # they reimplement OrgScopedRepository semantics (they ARE the cascade,
    # just in the wrong file).
    ("routers/applications.py", 167, "ApplicationRepository cascade override; phase 6 relocates"),
    ("routers/applications.py", 171, "ApplicationRepository cascade override; phase 6 relocates"),
    ("routers/config.py", 83, "ConfigRepository cascade override; phase 5 absorbs into base"),
    ("routers/config.py", 85, "ConfigRepository cascade override; phase 5 absorbs into base"),
    ("routers/config.py", 92, "ConfigRepository cascade override; phase 5 absorbs into base"),
    ("routers/config.py", 93, "ConfigRepository cascade override; phase 5 absorbs into base"),
    ("routers/config.py", 97, "ConfigRepository cascade override; phase 5 absorbs into base"),
    ("routers/config.py", 145, "ConfigRepository cascade override; phase 5 absorbs into base"),
    ("routers/tables.py", 241, "TableRepository cascade override; phase 6 relocates"),
    ("routers/tables.py", 244, "TableRepository cascade override; phase 6 relocates"),
    ("routers/tables.py", 266, "TableRepository cascade override; phase 6 relocates"),

    # --- Inline cascades the migration phases will remove ---
    # SDK Tables endpoints — phase 6 migrates to TableRepository.get/list.
    ("routers/cli.py", 2537, "cli_create_table uniqueness check; phase 6 migrates"),
    ("routers/cli.py", 2599, "cli_list_tables inline cascade; phase 6 migrates"),
    ("routers/cli.py", 2600, "cli_list_tables inline cascade; phase 6 migrates"),
    ("routers/cli.py", 2604, "cli_list_tables inline cascade; phase 6 migrates"),

    # SDK Config endpoints — phase 5 migrates to ConfigRepository.
    ("routers/cli.py", 517, "cli config_set inline; phase 5 migrates"),
    ("routers/cli.py", 615, "cli config_delete inline; phase 5 migrates"),

    # Workflows endpoint cascade — uses WorkflowRepository elsewhere but
    # has its own inline filtering for the listing endpoint. Phase 6 sweep.
    ("routers/workflows.py", 395, "workflows list inline cascade; phase 6 migrates"),
    ("routers/workflows.py", 398, "workflows list inline cascade; phase 6 migrates"),
    ("routers/workflows.py", 403, "workflows list inline cascade; phase 6 migrates"),
    ("routers/workflows.py", 404, "workflows list inline cascade; phase 6 migrates"),
    ("routers/workflows.py", 531, "workflow detail forms filter; phase 6 migrates"),
    ("routers/workflows.py", 584, "workflow detail agents filter; phase 6 migrates"),
    ("routers/workflows.py", 605, "workflow detail apps filter; phase 6 migrates"),

    # Agents endpoint — MCP connection lookup by org. Phase 6 sweep.
    ("routers/agents.py", 458, "agents MCPConnection lookup; phase 6 migrates via MCPConnectionRepository"),

    # Tools endpoint — Workflow list with cascade. Phase 6 sweep.
    ("routers/tools.py", 111, "tools workflow list; phase 6 migrates"),
    ("routers/tools.py", 113, "tools workflow list; phase 6 migrates"),

    # Websocket — Table org filter for subscription. Phase 6 sweep.
    ("routers/websocket.py", 95, "websocket table subscription filter; phase 6 migrates"),
    ("routers/websocket.py", 96, "websocket table subscription filter; phase 6 migrates"),

    # Tables endpoint — custom claim cross-reference. Phase 6 sweep.
    ("routers/tables.py", 694, "tables custom claim cross-ref; phase 6 migrates via CustomClaimRepository"),

    # Claims router — CustomClaim and Table lookups; phase 6 migrates.
    ("routers/claims.py", 68, "claim table lookup; phase 6 migrates"),
    ("routers/claims.py", 95, "claim refs lookup; phase 6 migrates"),
    ("routers/claims.py", 116, "claim list query; phase 6 migrates via CustomClaimRepository"),
    ("routers/claims.py", 135, "claim table access cross-ref; phase 6 migrates"),
    ("routers/claims.py", 177, "claim list with filter; phase 6 migrates"),
    ("routers/claims.py", 196, "claim get-by-name; phase 6 migrates"),
    ("routers/claims.py", 271, "claim update-by-name; phase 6 migrates"),
    ("routers/claims.py", 319, "claim delete-by-name; phase 6 migrates"),

    # Knowledge Sources router — KnowledgeStore lookups; phase 6 migrates.
    ("routers/knowledge_sources.py", 137, "knowledge namespace role lookup; phase 6 migrates"),
    ("routers/knowledge_sources.py", 219, "knowledge stores list global; phase 6 migrates"),
    ("routers/knowledge_sources.py", 221, "knowledge stores list scoped; phase 6 migrates"),
    ("routers/knowledge_sources.py", 225, "knowledge stores cascade; phase 6 migrates"),
    ("routers/knowledge_sources.py", 226, "knowledge stores cascade; phase 6 migrates"),
    ("routers/knowledge_sources.py", 301, "knowledge store target lookup; phase 6 migrates"),
    ("routers/knowledge_sources.py", 363, "knowledge stores list global (2); phase 6 migrates"),
    ("routers/knowledge_sources.py", 365, "knowledge stores list scoped (2); phase 6 migrates"),
    ("routers/knowledge_sources.py", 369, "knowledge stores cascade (2); phase 6 migrates"),
    ("routers/knowledge_sources.py", 370, "knowledge stores cascade (2); phase 6 migrates"),
    ("routers/knowledge_sources.py", 520, "knowledge store target lookup (2); phase 6 migrates"),

    # MCP Connections router — phase 6 migrates via MCPConnectionRepository.
    ("routers/mcp_connections.py", 459, "MCP connection org filter; phase 6 migrates"),

    # OAuth Connections router — phase 4 migrates via OAuthProvider/TokenRepository.
    ("routers/oauth_connections.py", 145, "OAuthProvider cascade; phase 4 migrates"),
    ("routers/oauth_connections.py", 146, "OAuthProvider cascade; phase 4 migrates"),
    ("routers/oauth_connections.py", 150, "OAuthProvider global filter; phase 4 migrates"),
    ("routers/oauth_connections.py", 288, "OAuthToken scoped filter; phase 4 migrates"),
    ("routers/oauth_connections.py", 290, "OAuthToken global filter; phase 4 migrates"),

    # Integrations router — ConfigModel lookups for integration config storage;
    # phase 5 migrates via ConfigRepository.
    ("routers/integrations.py", 301, "integration mapping cascade; phase 6 migrates"),
    ("routers/integrations.py", 437, "integration config global lookup; phase 5 migrates"),
    ("routers/integrations.py", 443, "integration config org lookup; phase 5 migrates"),
    ("routers/integrations.py", 565, "integration config global lookup (2); phase 5 migrates"),
    ("routers/integrations.py", 589, "integration config org lookup (2); phase 5 migrates"),

    # Export/Import router — manifest sync touches every execution-resolution
    # entity. Migrating these is in scope for phase 8 follow-up
    # (manifest sync _resolve_* audit). Allow-listed until then.
    ("routers/export_import.py", 334, "manifest sync config cascade; phase 8 follow-up"),
    ("routers/export_import.py", 336, "manifest sync config cascade; phase 8 follow-up"),
    ("routers/export_import.py", 359, "manifest sync config global filter; phase 8 follow-up"),
    ("routers/export_import.py", 551, "manifest sync knowledge org lookup; phase 8 follow-up"),
    ("routers/export_import.py", 553, "manifest sync knowledge global filter; phase 8 follow-up"),
    ("routers/export_import.py", 622, "manifest sync table org lookup; phase 8 follow-up"),
    ("routers/export_import.py", 624, "manifest sync table global filter; phase 8 follow-up"),
    ("routers/export_import.py", 757, "manifest sync config org lookup; phase 8 follow-up"),
    ("routers/export_import.py", 759, "manifest sync config global filter; phase 8 follow-up"),
    ("routers/export_import.py", 918, "manifest sync mapping org lookup; phase 8 follow-up"),
    ("routers/export_import.py", 920, "manifest sync mapping global filter; phase 8 follow-up"),
    ("routers/export_import.py", 1117, "manifest sync config org check; phase 8 follow-up"),
    ("routers/export_import.py", 1119, "manifest sync config global check; phase 8 follow-up"),

    # --- Identity-entity scope filters (legitimate; permanent allow-list) ---
    # Reports filter aggregated telemetry by org. These tables are identity
    # entities (no cascade), so the filter is a normal WHERE on a column
    # value, not a cascade query.
    ("routers/usage_reports.py", 84, "AIUsage identity-entity scope filter"),
    ("routers/usage_reports.py", 115, "Execution identity-entity scope filter"),
    ("routers/usage_reports.py", 182, "AIUsage identity-entity scope filter"),
    ("routers/usage_reports.py", 223, "AIUsage identity-entity scope filter"),
    ("routers/usage_reports.py", 263, "AIUsage identity-entity scope filter"),
    ("routers/usage_reports.py", 296, "AIUsage join to Organization"),
    ("routers/usage_reports.py", 353, "KnowledgeStorageDaily join to Organization"),
    ("routers/usage_reports.py", 362, "KnowledgeStorageDaily identity-entity scope filter"),
    ("routers/usage_reports.py", 393, "KnowledgeStorageDaily identity-entity scope filter"),
    ("routers/roi_reports.py", 121, "ExecutionMetricsDaily identity-entity scope filter"),
    ("routers/roi_reports.py", 123, "ExecutionMetricsDaily identity-entity scope filter"),
    ("routers/roi_reports.py", 231, "WorkflowROIDaily identity-entity scope filter"),
    ("routers/roi_reports.py", 233, "WorkflowROIDaily identity-entity scope filter"),
    ("routers/roi_reports.py", 310, "ExecutionMetricsDaily join to Organization"),
    ("routers/roi_reports.py", 436, "ExecutionMetricsDaily identity-entity scope filter"),
    ("routers/roi_reports.py", 438, "ExecutionMetricsDaily identity-entity scope filter"),
    ("routers/executions.py", 79, "Execution identity-entity scope filter"),
    ("routers/metrics.py", 234, "ExecutionMetricsDaily identity-entity scope filter"),
    ("routers/metrics.py", 237, "ExecutionMetricsDaily identity-entity scope filter"),
    ("routers/metrics.py", 314, "ExecutionMetricsDaily join to Organization"),
    ("routers/metrics.py", 389, "ExecutionMetricsDaily identity-entity scope filter"),
    ("routers/users.py", 91, "User identity-entity scope filter"),
    ("routers/users.py", 94, "User identity-entity scope filter"),
    ("routers/users.py", 97, "User identity-entity scope filter"),
    ("routers/roles.py", 1072, "KnowledgeNamespaceRole identity-entity scope filter"),

    # --- SystemConfig admin endpoints (permanent for now) ---
    # SystemConfig is execution-resolution but has admin-only access patterns
    # that pre-date the repository. Phase 6+ may migrate; allow-listed today.
    ("routers/llm_config.py", 330, "SystemConfig admin lookup; pre-repo pattern"),
    ("routers/llm_config.py", 405, "SystemConfig admin lookup; pre-repo pattern"),
    ("routers/llm_config.py", 433, "SystemConfig admin lookup; pre-repo pattern"),
    ("routers/llm_config.py", 617, "SystemConfig admin lookup; pre-repo pattern"),
    ("routers/llm_config.py", 666, "SystemConfig admin lookup; pre-repo pattern"),
    ("routers/llm_config.py", 753, "SystemConfig admin lookup; pre-repo pattern"),
    ("routers/llm_config.py", 767, "SystemConfig admin lookup; pre-repo pattern"),
    ("routers/oauth_connections.py", 1155, "SystemConfig admin lookup; pre-repo pattern"),
    ("routers/oauth_connections.py", 1218, "SystemConfig admin lookup; pre-repo pattern"),

    # --- Documentation strings (cli.py module docstring) ---
    # The module docstring describes inline cascades as something to avoid.
    # Matching text in a string literal trips the regex. Allow-listed.
    ("routers/cli.py", 17, "module docstring describing what NOT to do"),
}


def _scan_file_for_inline_org(file_path: Path) -> list[tuple[int, str]]:
    """Return (line_number, content) for every inline org reference."""
    findings: list[tuple[int, str]] = []
    text = file_path.read_text()
    for line_number, line in enumerate(text.splitlines(), start=1):
        if _INLINE_ORG_RE.search(line):
            findings.append((line_number, line.strip()))
    return findings


class TestNoInlineOrgScopingInRouters:
    """Routers MUST NOT contain raw organization_id comparisons.

    Use OrgScopedRepository. The cascade primitive lives in the base class.
    """

    def test_routers_have_no_unallowlisted_inline_org_filters(self) -> None:
        violations: list[tuple[str, int, str]] = []

        for py_file in sorted(ROUTERS_DIR.rglob("*.py")):
            rel = py_file.relative_to(API_ROOT).as_posix()
            for line_number, content in _scan_file_for_inline_org(py_file):
                # Check allow-list (file, line) ignoring the reason column.
                allowlisted = any(
                    rel == entry[0] and line_number == entry[1]
                    for entry in ALLOW_LIST_INLINE_ORG
                )
                if not allowlisted:
                    violations.append((rel, line_number, content))

        if violations:
            details = "\n".join(
                f"  {file}:{line}  {content}" for file, line, content in violations
            )
            pytest.fail(
                "Found inline organization_id filters in routers that are not on "
                "the allow-list. Either migrate the code to OrgScopedRepository "
                "(see api/src/repositories/README.md) or, if legitimate, add an "
                f"allow-list entry with a one-line justification:\n{details}"
            )


# ---------------------------------------------------------------------------
# Test 2: Org-scoped models have a repository
# ---------------------------------------------------------------------------


# Models that are identity entities — they carry organization_id but are NOT
# resolved by cascade. They do NOT need an OrgScopedRepository subclass.
# See api/src/repositories/README.md for the classification table.
IDENTITY_MODELS: set[str] = {
    "Execution",
    "ExecutionMetricsDaily",
    "WorkflowROIDaily",
    "KnowledgeStorageDaily",
    "User",
    "AIUsage",
    "KnowledgeNamespaceRole",
    "Event",
    "AuditLog",
}


# Models that ARE execution-resolution and must have an OrgScopedRepository
# subclass. The phase-4-onward migrations create the repos that aren't here
# yet; until they exist, those models are allow-listed.
EXECUTION_RESOLUTION_MODELS_WITHOUT_REPO_YET: set[str] = {
    "OAuthProvider",     # Phase 4: OAuthProviderRepository
    "OAuthToken",        # Phase 4: OAuthTokenRepository
    "SystemConfig",      # Future: SystemConfigRepository (post-phase-5)
    "EventSource",       # Future: EventSourceRepository (post-phase-6)
    "CustomClaim",       # Future: CustomClaimRepository (post-phase-6)
    "MCPConnection",     # Existing MCPConnectionRepository but check confirms
    "MCPServer",         # Existing MCPServerRepository but check confirms
}


def _models_with_org_id() -> dict[str, Path]:
    """Return {ClassName: file_path} for every Base subclass that declares
    an organization_id column."""
    found: dict[str, Path] = {}
    for py_file in sorted(MODELS_ORM_DIR.rglob("*.py")):
        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            # Must be a Base subclass (any base named "Base")
            is_base_subclass = any(
                isinstance(b, ast.Name) and b.id == "Base"
                for b in node.bases
            )
            if not is_base_subclass:
                continue

            for stmt in node.body:
                # Looking for `organization_id: Mapped[...] = mapped_column(...)`.
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    if stmt.target.id == "organization_id":
                        found[node.name] = py_file
                        break

    return found


def _file_import_aliases(tree: ast.AST) -> dict[str, str]:
    """Return {local_name: original_name} for every `from X import Y as Z`."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
    return aliases


def _repository_subclasses() -> set[str]:
    """Return the set of ORM model names that have an OrgScopedRepository
    subclass somewhere in api/src/. Resolves `import X as Y` aliases so a
    declaration like `OrgScopedRepository[FormORM]` (where FormORM is
    `Form` aliased) maps back to `Form`."""
    bound: set[str] = set()
    for py_file in API_ROOT.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue

        aliases = _file_import_aliases(tree)

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                if (
                    isinstance(base, ast.Subscript)
                    and isinstance(base.value, ast.Name)
                    and base.value.id == "OrgScopedRepository"
                    and isinstance(base.slice, ast.Name)
                ):
                    type_param = base.slice.id
                    # If the type-param was an alias, resolve to the original.
                    bound.add(aliases.get(type_param, type_param))
    return bound


class TestOrgScopedModelsHaveRepository:
    """Every ORM model with organization_id must be classified.

    Either it has an OrgScopedRepository subclass (execution-resolution),
    OR it's on the IDENTITY_MODELS allow-list (identity entity).

    Adding an org-scoped model without classification fails this test.
    """

    def test_all_org_id_models_classified(self) -> None:
        models_with_org_id = _models_with_org_id()
        repos = _repository_subclasses()

        unclassified: list[tuple[str, str]] = []
        for model_name, file_path in models_with_org_id.items():
            if model_name in IDENTITY_MODELS:
                continue
            if model_name in repos:
                continue
            if model_name in EXECUTION_RESOLUTION_MODELS_WITHOUT_REPO_YET:
                continue
            unclassified.append((model_name, file_path.relative_to(API_ROOT).as_posix()))

        if unclassified:
            details = "\n".join(
                f"  {model} in {file}" for model, file in unclassified
            )
            pytest.fail(
                "ORM models with organization_id that are not classified.\n"
                "Either:\n"
                "  - Add an OrgScopedRepository subclass (if execution-resolution), or\n"
                "  - Add the model name to IDENTITY_MODELS in this test (if identity).\n"
                "See api/src/repositories/README.md for the classification rule.\n"
                f"Unclassified models:\n{details}"
            )

    def test_identity_models_actually_exist(self) -> None:
        """If an entry in IDENTITY_MODELS no longer exists in the ORM,
        the allow-list has drifted and needs cleanup."""
        models_with_org_id = set(_models_with_org_id().keys())
        stale = IDENTITY_MODELS - models_with_org_id
        if stale:
            pytest.fail(
                "IDENTITY_MODELS contains entries that no longer have "
                f"organization_id columns (or no longer exist): {sorted(stale)}. "
                "Remove them from the allow-list."
            )

    def test_no_overlap_between_buckets(self) -> None:
        """A model can't be both identity and execution-resolution."""
        overlap = IDENTITY_MODELS & EXECUTION_RESOLUTION_MODELS_WITHOUT_REPO_YET
        assert not overlap, (
            f"Models classified as BOTH identity and execution-resolution: {overlap}. "
            "Pick one."
        )


# ---------------------------------------------------------------------------
# Test 3: SDK endpoints that accept `scope` call resolve_effective_scope
# ---------------------------------------------------------------------------


SDK_ROUTER_FILES = {
    # When phase 7 renames /api/cli/* to /api/sdk/*, update this list.
    ROUTERS_DIR / "cli.py",
}


# Endpoints under /api/cli/* that do NOT touch execution-resolution entities
# and therefore don't need to call resolve_effective_scope. The path keys
# below are used to identify them via the @router decorator.
EXEMPT_SDK_ENDPOINTS: dict[str, str] = {
    # Auth and session
    "/auth/login": "auth — caller identity IS the input",
    "/auth/refresh": "auth — token refresh, no scope",
    "/auth/whoami": "auth — current user lookup",
    "/context": "developer context — does its own platform-admin gate",
    # Health, version, capabilities
    "/version": "health/version, no org data",
    "/download": "CLI binary download, no org data",
    # CLI session lifecycle
    "/sessions/register": "CLI session bootstrap, no org data",
    "/sessions/state": "CLI session state lookup",
    "/sessions/continue": "CLI session continuation",
    "/sessions/pending": "CLI session work pickup",
    "/sessions/log": "CLI session log write",
    "/sessions/result": "CLI session result write",
}


class TestSDKEndpointsUseResolver:
    """SDK endpoints that take a `scope` parameter must call
    resolve_effective_scope (or be on the exempt list).

    This test is the **placeholder skeleton** — the migration phases (4-7)
    convert endpoints onto resolve_effective_scope and shrink the exempt
    list. Today, the function does not exist as a caller yet, so this
    test only verifies the infrastructure: the file exists, the test can
    parse it, and the exempt list is well-formed.

    A future iteration of this test (post-phase-1 migration) will assert
    that every non-exempt endpoint with a `scope` field actually invokes
    `resolve_effective_scope`. That's intentionally NOT done now because:

    1. No endpoints call the resolver yet — phase 4 introduces the first
       caller.
    2. Adding the strict check before any callers exist would require
       allow-listing every existing scope-taking endpoint, defeating the
       purpose.

    What this test enforces today:
      - The resolver module exists and can be imported.
      - The exempt list is well-formed.

    What it will enforce after phase 4:
      - Each non-exempt SDK endpoint accepting scope calls resolve_effective_scope.
    """

    def test_resolver_module_importable(self) -> None:
        from shared.scope_resolver import resolve_effective_scope

        assert callable(resolve_effective_scope)

    def test_exempt_list_well_formed(self) -> None:
        for path, reason in EXEMPT_SDK_ENDPOINTS.items():
            assert path.startswith("/"), f"Exempt endpoint path must be absolute: {path}"
            assert reason, f"Exempt endpoint {path} needs a one-line justification"

    def test_sdk_router_files_exist(self) -> None:
        for path in SDK_ROUTER_FILES:
            assert path.exists(), f"SDK router file missing: {path}"
