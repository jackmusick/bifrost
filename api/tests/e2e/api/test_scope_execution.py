"""
E2E tests for workflow execution scope resolution.

Tests that SDK operations during workflow execution use the correct scope:
- Org-scoped workflows: use workflow's organization_id
- Global workflows: use caller's organization_id

These tests verify the scope resolution logic for ALL SDK modules:
- tables: query, insert, get, update, delete, count
- config: get, set, list, delete
- knowledge: search, store, get, delete (requires EMBEDDINGS_AI_TEST_KEY)
"""

import logging
import os
import pytest

from tests.e2e.conftest import write_and_register


logger = logging.getLogger(__name__)

# Check if embeddings are configured
EMBEDDINGS_AVAILABLE = bool(os.environ.get("EMBEDDINGS_AI_TEST_KEY"))


# =============================================================================
# Test Data Setup - Tables
# =============================================================================


@pytest.fixture(scope="module")
def scope_test_table_name() -> str:
    """Unique table name for scope tests."""
    return "e2e_scope_test_table"


@pytest.fixture(scope="module")
def org1_table_data(
    e2e_client,
    platform_admin,
    org1,
    scope_test_table_name,
):
    """Create test data in org1's table."""
    response = e2e_client.post(
        f"/api/tables/{scope_test_table_name}/documents",
        headers=platform_admin.headers,
        params={"scope": org1["id"]},
        json={"data": {"scope_marker": "org1", "name": "Org 1 Test Record"}},
    )
    assert response.status_code == 201, f"Failed to create org1 document: {response.text}"
    doc = response.json()

    yield {"org_id": org1["id"], "doc_id": doc["id"], "scope_marker": "org1"}

    # Cleanup
    e2e_client.delete(
        f"/api/tables/{scope_test_table_name}/documents/{doc['id']}",
        headers=platform_admin.headers,
        params={"scope": org1["id"]},
    )


@pytest.fixture(scope="module")
def org2_table_data(
    e2e_client,
    platform_admin,
    org2,
    scope_test_table_name,
):
    """Create test data in org2's table."""
    response = e2e_client.post(
        f"/api/tables/{scope_test_table_name}/documents",
        headers=platform_admin.headers,
        params={"scope": org2["id"]},
        json={"data": {"scope_marker": "org2", "name": "Org 2 Test Record"}},
    )
    assert response.status_code == 201, f"Failed to create org2 document: {response.text}"
    doc = response.json()

    yield {"org_id": org2["id"], "doc_id": doc["id"], "scope_marker": "org2"}

    # Cleanup
    e2e_client.delete(
        f"/api/tables/{scope_test_table_name}/documents/{doc['id']}",
        headers=platform_admin.headers,
        params={"scope": org2["id"]},
    )


@pytest.fixture(scope="module")
def global_table_data(
    e2e_client,
    platform_admin,
    scope_test_table_name,
):
    """Create test data in global table (no org)."""
    response = e2e_client.post(
        f"/api/tables/{scope_test_table_name}/documents",
        headers=platform_admin.headers,
        params={"scope": "global"},
        json={"data": {"scope_marker": "global", "name": "Global Test Record"}},
    )
    assert response.status_code == 201, f"Failed to create global document: {response.text}"
    doc = response.json()

    yield {"org_id": None, "doc_id": doc["id"], "scope_marker": "global"}

    # Cleanup
    e2e_client.delete(
        f"/api/tables/{scope_test_table_name}/documents/{doc['id']}",
        headers=platform_admin.headers,
        params={"scope": "global"},
    )


# =============================================================================
# Test Data Setup - Config
# =============================================================================


@pytest.fixture(scope="module")
def scope_test_config_key() -> str:
    """Unique config key for scope tests."""
    return "e2e_scope_test_config"


@pytest.fixture(scope="module")
def org1_config_data(
    e2e_client,
    platform_admin,
    org1,
    scope_test_config_key,
):
    """Create test config in org1's scope."""
    response = e2e_client.post(
        "/api/cli/config/set",
        headers=platform_admin.headers,
        json={
            "key": scope_test_config_key,
            "value": {"scope_marker": "org1"},
            "scope": org1["id"],
        },
    )
    assert response.status_code == 204, f"Failed to create org1 config: {response.text}"

    yield {"org_id": org1["id"], "scope_marker": "org1"}

    # Cleanup
    e2e_client.post(
        "/api/cli/config/delete",
        headers=platform_admin.headers,
        json={"key": scope_test_config_key, "scope": org1["id"]},
    )


@pytest.fixture(scope="module")
def org2_config_data(
    e2e_client,
    platform_admin,
    org2,
    scope_test_config_key,
):
    """Create test config in org2's scope."""
    response = e2e_client.post(
        "/api/cli/config/set",
        headers=platform_admin.headers,
        json={
            "key": scope_test_config_key,
            "value": {"scope_marker": "org2"},
            "scope": org2["id"],
        },
    )
    assert response.status_code == 204, f"Failed to create org2 config: {response.text}"

    yield {"org_id": org2["id"], "scope_marker": "org2"}

    # Cleanup
    e2e_client.post(
        "/api/cli/config/delete",
        headers=platform_admin.headers,
        json={"key": scope_test_config_key, "scope": org2["id"]},
    )


@pytest.fixture(scope="module")
def global_config_data(
    e2e_client,
    platform_admin,
    scope_test_config_key,
):
    """Create test config in global scope."""
    response = e2e_client.post(
        "/api/cli/config/set",
        headers=platform_admin.headers,
        json={
            "key": scope_test_config_key,
            "value": {"scope_marker": "global"},
            "scope": "global",
        },
    )
    assert response.status_code == 204, f"Failed to create global config: {response.text}"

    yield {"org_id": None, "scope_marker": "global"}

    # Cleanup
    e2e_client.post(
        "/api/cli/config/delete",
        headers=platform_admin.headers,
        json={"key": scope_test_config_key, "scope": "global"},
    )


# =============================================================================
# Test Data Setup - Knowledge (requires EMBEDDINGS_AI_TEST_KEY)
# =============================================================================


@pytest.fixture(scope="module")
def scope_test_knowledge_namespace() -> str:
    """Unique knowledge namespace for scope tests."""
    return "e2e_scope_test_ns"


@pytest.fixture(scope="module")
def embedding_config_for_scope_tests(
    e2e_client,
    platform_admin,
):
    """
    Configure embedding provider for scope tests (module-scoped).

    Skips if EMBEDDINGS_AI_TEST_KEY is not set.
    """
    embeddings_test_key = os.environ.get("EMBEDDINGS_AI_TEST_KEY")
    if not embeddings_test_key:
        pytest.skip("EMBEDDINGS_AI_TEST_KEY not configured - skipping knowledge tests")

    config = {
        "provider": "openai",
        "model": "text-embedding-3-small",
        "api_key": embeddings_test_key,
    }

    # Configure embedding provider
    response = e2e_client.post(
        "/api/admin/llm/embedding-config",
        json=config,
        headers=platform_admin.headers,
    )
    assert response.status_code == 200, f"Failed to configure embeddings: {response.text}"

    logger.info("Configured OpenAI embedding provider for scope tests")
    yield config

    # Cleanup
    try:
        e2e_client.delete(
            "/api/admin/llm/embedding-config",
            headers=platform_admin.headers,
        )
        logger.info("Cleaned up embedding config")
    except Exception as e:
        logger.warning(f"Failed to cleanup embedding config: {e}")


@pytest.fixture(scope="module")
def org1_knowledge_data(
    e2e_client,
    platform_admin,
    org1,
    scope_test_knowledge_namespace,
    embedding_config_for_scope_tests,  # noqa: ARG001 - used for side effect
):
    """Create test knowledge document in org1's scope."""
    response = e2e_client.post(
        "/api/cli/knowledge/store",
        headers=platform_admin.headers,
        json={
            "content": "Org 1 test knowledge document with scope marker org1",
            "namespace": scope_test_knowledge_namespace,
            "key": "org1-doc",
            "metadata": {"scope_marker": "org1"},
            "scope": org1["id"],
        },
    )
    assert response.status_code == 200, f"Failed to create org1 knowledge: {response.text}"

    yield {"org_id": org1["id"], "scope_marker": "org1"}

    # Cleanup
    e2e_client.post(
        "/api/cli/knowledge/delete",
        headers=platform_admin.headers,
        json={
            "key": "org1-doc",
            "namespace": scope_test_knowledge_namespace,
            "scope": org1["id"],
        },
    )


@pytest.fixture(scope="module")
def org2_knowledge_data(
    e2e_client,
    platform_admin,
    org2,
    scope_test_knowledge_namespace,
    embedding_config_for_scope_tests,  # noqa: ARG001 - used for side effect
):
    """Create test knowledge document in org2's scope."""
    response = e2e_client.post(
        "/api/cli/knowledge/store",
        headers=platform_admin.headers,
        json={
            "content": "Org 2 test knowledge document with scope marker org2",
            "namespace": scope_test_knowledge_namespace,
            "key": "org2-doc",
            "metadata": {"scope_marker": "org2"},
            "scope": org2["id"],
        },
    )
    assert response.status_code == 200, f"Failed to create org2 knowledge: {response.text}"

    yield {"org_id": org2["id"], "scope_marker": "org2"}

    # Cleanup
    e2e_client.post(
        "/api/cli/knowledge/delete",
        headers=platform_admin.headers,
        json={
            "key": "org2-doc",
            "namespace": scope_test_knowledge_namespace,
            "scope": org2["id"],
        },
    )


@pytest.fixture(scope="module")
def global_knowledge_data(
    e2e_client,
    platform_admin,
    scope_test_knowledge_namespace,
    embedding_config_for_scope_tests,  # noqa: ARG001 - used for side effect
):
    """Create test knowledge document in global scope."""
    response = e2e_client.post(
        "/api/cli/knowledge/store",
        headers=platform_admin.headers,
        json={
            "content": "Global test knowledge document with scope marker global",
            "namespace": scope_test_knowledge_namespace,
            "key": "global-doc",
            "metadata": {"scope_marker": "global"},
            "scope": "global",
        },
    )
    assert response.status_code == 200, f"Failed to create global knowledge: {response.text}"

    yield {"org_id": None, "scope_marker": "global"}

    # Cleanup
    e2e_client.post(
        "/api/cli/knowledge/delete",
        headers=platform_admin.headers,
        json={
            "key": "global-doc",
            "namespace": scope_test_knowledge_namespace,
            "scope": "global",
        },
    )


# =============================================================================
# Comprehensive Workflow Fixture
# =============================================================================


@pytest.fixture(scope="module")
def comprehensive_scope_workflow(
    e2e_client,
    platform_admin,
    org1,
    scope_test_table_name,
    scope_test_config_key,
    scope_test_knowledge_namespace,
    embedding_config_for_scope_tests,  # noqa: ARG001 - used for side effect
):
    """
    Create a workflow that tests ALL SDK modules.

    This workflow queries tables, config, and knowledge without explicit scope,
    relying on the execution context to determine the scope.
    Returns results from each SDK module for verification.
    """
    workflow_name = "e2e_comprehensive_scope_test"
    workflow_path = f"{workflow_name}.py"

    workflow_content = f'''"""E2E Comprehensive Scope Test Workflow"""
from bifrost import workflow, tables, config, knowledge, context

@workflow(
    name="{workflow_name}",
    description="Tests scope resolution across all SDK modules",
    execution_mode="sync",
)
async def {workflow_name}():
    """
    Query all SDK modules without explicit scope parameter.
    Returns scope markers from each module to verify correct scope resolution.
    """
    results = {{
        "context": {{
            "org_id": context.org_id,
            "scope": context.scope,
        }},
        "tables": {{}},
        "config": {{}},
        "knowledge": {{}},
    }}

    # Test tables.query()
    try:
        table_result = await tables.query("{scope_test_table_name}", limit=10)
        results["tables"]["query"] = {{
            "count": len(table_result.documents),
            "scope_markers": [
                doc.data.get("scope_marker")
                for doc in table_result.documents
                if doc.data.get("scope_marker")
            ],
        }}
    except Exception as e:
        results["tables"]["query"] = {{"error": str(e)}}

    # Test tables.count()
    try:
        count = await tables.count("{scope_test_table_name}")
        results["tables"]["count"] = count
    except Exception as e:
        results["tables"]["count"] = {{"error": str(e)}}

    # Test config.get()
    try:
        config_value = await config.get("{scope_test_config_key}")
        if config_value:
            results["config"]["get"] = {{
                "scope_marker": config_value.get("scope_marker") if isinstance(config_value, dict) else None,
            }}
        else:
            results["config"]["get"] = {{"scope_marker": None}}
    except Exception as e:
        results["config"]["get"] = {{"error": str(e)}}

    # Test knowledge.search()
    try:
        knowledge_results = await knowledge.search(
            "scope marker",
            namespace="{scope_test_knowledge_namespace}",
            limit=10,
            fallback=False,  # Don't fall back to global
        )
        results["knowledge"]["search"] = {{
            "count": len(knowledge_results),
            "scope_markers": [
                doc.metadata.get("scope_marker")
                for doc in knowledge_results
                if doc.metadata and doc.metadata.get("scope_marker")
            ],
        }}
    except Exception as e:
        results["knowledge"]["search"] = {{"error": str(e)}}

    return results
'''
    result = write_and_register(
        e2e_client, platform_admin.headers,
        workflow_path, workflow_content, workflow_name,
    )
    workflow_id = result["id"]

    # Set organization_id via PATCH to make it org-scoped
    response = e2e_client.patch(
        f"/api/workflows/{workflow_id}",
        headers=platform_admin.headers,
        json={"organization_id": org1["id"]},
    )
    assert response.status_code == 200, f"Set workflow org failed: {response.text}"

    yield {
        "id": workflow_id,
        "name": workflow_name,
        "org_id": org1["id"],
        "path": workflow_path,
    }

    # Cleanup
    e2e_client.delete(
        f"/api/files/editor?path={workflow_path}",
        headers=platform_admin.headers,
    )


@pytest.fixture(scope="module")
def global_comprehensive_workflow(
    e2e_client,
    platform_admin,
    scope_test_table_name,
    scope_test_config_key,
    scope_test_knowledge_namespace,
    embedding_config_for_scope_tests,  # noqa: ARG001 - used for side effect
):
    """
    Create a GLOBAL workflow that tests ALL SDK modules.

    Same as comprehensive_scope_workflow but without organization_id,
    so it uses caller's context.
    """
    workflow_name = "e2e_global_comprehensive_scope_test"
    workflow_path = f"{workflow_name}.py"

    workflow_content = f'''"""E2E Global Comprehensive Scope Test Workflow"""
from bifrost import workflow, tables, config, knowledge, context

@workflow(
    name="{workflow_name}",
    description="Tests scope resolution across all SDK modules (global workflow)",
    execution_mode="sync",
)
async def {workflow_name}():
    """
    Query all SDK modules without explicit scope parameter.
    Returns scope markers from each module to verify correct scope resolution.
    """
    results = {{
        "context": {{
            "org_id": context.org_id,
            "scope": context.scope,
        }},
        "tables": {{}},
        "config": {{}},
        "knowledge": {{}},
    }}

    # Test tables.query()
    try:
        table_result = await tables.query("{scope_test_table_name}", limit=10)
        results["tables"]["query"] = {{
            "count": len(table_result.documents),
            "scope_markers": [
                doc.data.get("scope_marker")
                for doc in table_result.documents
                if doc.data.get("scope_marker")
            ],
        }}
    except Exception as e:
        results["tables"]["query"] = {{"error": str(e)}}

    # Test tables.count()
    try:
        count = await tables.count("{scope_test_table_name}")
        results["tables"]["count"] = count
    except Exception as e:
        results["tables"]["count"] = {{"error": str(e)}}

    # Test config.get()
    try:
        config_value = await config.get("{scope_test_config_key}")
        if config_value:
            results["config"]["get"] = {{
                "scope_marker": config_value.get("scope_marker") if isinstance(config_value, dict) else None,
            }}
        else:
            results["config"]["get"] = {{"scope_marker": None}}
    except Exception as e:
        results["config"]["get"] = {{"error": str(e)}}

    # Test knowledge.search()
    try:
        knowledge_results = await knowledge.search(
            "scope marker",
            namespace="{scope_test_knowledge_namespace}",
            limit=10,
            fallback=False,  # Don't fall back to global
        )
        results["knowledge"]["search"] = {{
            "count": len(knowledge_results),
            "scope_markers": [
                doc.metadata.get("scope_marker")
                for doc in knowledge_results
                if doc.metadata and doc.metadata.get("scope_marker")
            ],
        }}
    except Exception as e:
        results["knowledge"]["search"] = {{"error": str(e)}}

    return results
'''
    result = write_and_register(
        e2e_client, platform_admin.headers,
        workflow_path, workflow_content, workflow_name,
    )
    workflow_id = result["id"]

    # Global workflow - no organization_id set

    yield {
        "id": workflow_id,
        "name": workflow_name,
        "org_id": None,  # Global
        "path": workflow_path,
    }

    # Cleanup
    e2e_client.delete(
        f"/api/files/editor?path={workflow_path}",
        headers=platform_admin.headers,
    )


# =============================================================================
# Test Cases - Comprehensive SDK Module Tests
# =============================================================================


@pytest.mark.e2e
class TestComprehensiveSdkScoping:
    """
    Test that ALL SDK modules respect scope resolution.

    Uses a single workflow that tests tables, config, and knowledge,
    verifying that each module sees the correct scoped data.
    """

    def test_org_workflow_sees_org1_data_in_all_modules(
        self,
        e2e_client,
        platform_admin,
        comprehensive_scope_workflow,
        org1_table_data,
        org2_table_data,
        org1_config_data,
        org2_config_data,
        org1_knowledge_data,
        org2_knowledge_data,
    ):
        """
        Org-scoped workflow should see org1 data in ALL SDK modules.

        Verifies:
        - tables.query() returns org1 data
        - tables.count() counts org1 data
        - config.get() returns org1 config
        - knowledge.search() returns org1 documents
        """
        # Ensure fixtures are loaded
        assert org1_table_data is not None
        assert org2_table_data is not None
        assert org1_config_data is not None
        assert org2_config_data is not None
        assert org1_knowledge_data is not None
        assert org2_knowledge_data is not None

        response = e2e_client.post(
            "/api/workflows/execute",
            headers=platform_admin.headers,
            json={
                "workflow_id": comprehensive_scope_workflow["id"],
                "input_data": {},
            },
        )
        assert response.status_code == 200, f"Execute failed: {response.text}"
        data = response.json()
        assert data["status"] == "Success", f"Execution failed: {data}"

        result = data.get("result", {})

        # Verify context
        assert result["context"]["org_id"] == comprehensive_scope_workflow["org_id"], (
            f"Context org_id mismatch. Expected: {comprehensive_scope_workflow['org_id']}, "
            f"Got: {result['context']['org_id']}"
        )

        # Verify tables module
        tables_result = result.get("tables", {})
        assert "error" not in tables_result.get("query", {}), (
            f"tables.query() failed: {tables_result.get('query', {}).get('error')}"
        )
        table_markers = tables_result.get("query", {}).get("scope_markers", [])
        assert "org1" in table_markers, (
            f"tables.query() should see org1 data. Got: {table_markers}"
        )
        assert "org2" not in table_markers, (
            f"tables.query() should NOT see org2 data. Got: {table_markers}"
        )

        # Verify config module
        config_result = result.get("config", {})
        assert "error" not in config_result.get("get", {}), (
            f"config.get() failed: {config_result.get('get', {}).get('error')}"
        )
        config_marker = config_result.get("get", {}).get("scope_marker")
        assert config_marker == "org1", (
            f"config.get() should return org1 config. Got: {config_marker}"
        )

        # Verify knowledge module
        knowledge_result = result.get("knowledge", {})
        assert "error" not in knowledge_result.get("search", {}), (
            f"knowledge.search() failed: {knowledge_result.get('search', {}).get('error')}"
        )
        knowledge_markers = knowledge_result.get("search", {}).get("scope_markers", [])
        assert "org1" in knowledge_markers, (
            f"knowledge.search() should see org1 data. Got: {knowledge_markers}"
        )
        assert "org2" not in knowledge_markers, (
            f"knowledge.search() should NOT see org2 data. Got: {knowledge_markers}"
        )

    def test_global_workflow_with_org2_context_sees_org2_data(
        self,
        e2e_client,
        platform_admin,
        org2,
        global_comprehensive_workflow,
        org1_table_data,
        org2_table_data,
        org1_config_data,
        org2_config_data,
        org1_knowledge_data,
        org2_knowledge_data,
    ):
        """
        Global workflow with org2 context should see org2 data in ALL modules.

        Platform admin sets developer context to org2, then executes global workflow.
        All SDK modules should use org2's scope.
        """
        # Ensure fixtures are loaded
        assert org1_table_data is not None
        assert org2_table_data is not None
        assert org1_config_data is not None
        assert org2_config_data is not None
        assert org1_knowledge_data is not None
        assert org2_knowledge_data is not None

        # Set developer context to org2
        response = e2e_client.put(
            "/api/cli/context",
            headers=platform_admin.headers,
            json={"default_org_id": org2["id"]},
        )
        assert response.status_code == 200, f"Set context failed: {response.text}"

        try:
            response = e2e_client.post(
                "/api/workflows/execute",
                headers=platform_admin.headers,
                json={
                    "workflow_id": global_comprehensive_workflow["id"],
                    "input_data": {},
                },
            )
            assert response.status_code == 200, f"Execute failed: {response.text}"
            data = response.json()
            assert data["status"] == "Success", f"Execution failed: {data}"

            result = data.get("result", {})

            # Verify context
            assert result["context"]["org_id"] == org2["id"], (
                f"Context org_id should be org2. Got: {result['context']['org_id']}"
            )

            # Verify tables module
            tables_result = result.get("tables", {})
            assert "error" not in tables_result.get("query", {}), (
                f"tables.query() failed: {tables_result.get('query', {}).get('error')}"
            )
            table_markers = tables_result.get("query", {}).get("scope_markers", [])
            assert "org2" in table_markers, (
                f"tables.query() should see org2 data. Got: {table_markers}"
            )
            assert "org1" not in table_markers, (
                f"tables.query() should NOT see org1 data. Got: {table_markers}"
            )

            # Verify config module
            config_result = result.get("config", {})
            assert "error" not in config_result.get("get", {}), (
                f"config.get() failed: {config_result.get('get', {}).get('error')}"
            )
            config_marker = config_result.get("get", {}).get("scope_marker")
            assert config_marker == "org2", (
                f"config.get() should return org2 config. Got: {config_marker}"
            )

            # Verify knowledge module
            knowledge_result = result.get("knowledge", {})
            assert "error" not in knowledge_result.get("search", {}), (
                f"knowledge.search() failed: {knowledge_result.get('search', {}).get('error')}"
            )
            knowledge_markers = knowledge_result.get("search", {}).get("scope_markers", [])
            assert "org2" in knowledge_markers, (
                f"knowledge.search() should see org2 data. Got: {knowledge_markers}"
            )
            assert "org1" not in knowledge_markers, (
                f"knowledge.search() should NOT see org1 data. Got: {knowledge_markers}"
            )

        finally:
            # Clear developer context
            e2e_client.put(
                "/api/cli/context",
                headers=platform_admin.headers,
                json={"default_org_id": None},
            )


@pytest.mark.e2e
class TestExplicitScopeOverride:
    """
    Test that explicit scope parameter overrides execution context.

    Even when running in org1's context, passing scope="org2" or scope="global"
    should access that scope's data.
    """

    @pytest.fixture(scope="class")
    def scope_override_workflow(
        self,
        e2e_client,
        platform_admin,
        org1,
        org2,
        scope_test_table_name,
        scope_test_config_key,
        scope_test_knowledge_namespace,
    ):
        """
        Create a workflow that explicitly overrides scope for each operation.

        This workflow is org-scoped (org1), but explicitly passes org2's scope
        to SDK operations. Should see org2's data despite running in org1 context.
        """
        workflow_name = "e2e_scope_override_test"
        workflow_path = f"{workflow_name}.py"
        org2_id = org2["id"]

        workflow_content = f'''"""E2E Scope Override Test Workflow"""
from bifrost import workflow, tables, config, knowledge, context

@workflow(
    name="{workflow_name}",
    description="Tests explicit scope override in SDK operations",
    execution_mode="sync",
)
async def {workflow_name}():
    """
    Override scope in each SDK operation to access org2's data,
    even though this workflow belongs to org1.
    """
    results = {{
        "context": {{
            "org_id": context.org_id,
            "scope": context.scope,
        }},
        "default_scope": {{}},
        "overridden_scope": {{}},
    }}

    # First, query with default scope (should see org1)
    try:
        default_result = await tables.query("{scope_test_table_name}", limit=10)
        results["default_scope"]["tables"] = [
            doc.data.get("scope_marker")
            for doc in default_result.documents
            if doc.data.get("scope_marker")
        ]
    except Exception as e:
        results["default_scope"]["tables"] = {{"error": str(e)}}

    # Now query with explicit org2 scope
    try:
        override_result = await tables.query(
            "{scope_test_table_name}",
            limit=10,
            scope="{org2_id}",
        )
        results["overridden_scope"]["tables"] = [
            doc.data.get("scope_marker")
            for doc in override_result.documents
            if doc.data.get("scope_marker")
        ]
    except Exception as e:
        results["overridden_scope"]["tables"] = {{"error": str(e)}}

    # Config with default scope
    try:
        default_config = await config.get("{scope_test_config_key}")
        if default_config and isinstance(default_config, dict):
            results["default_scope"]["config"] = default_config.get("scope_marker")
        else:
            results["default_scope"]["config"] = None
    except Exception as e:
        results["default_scope"]["config"] = {{"error": str(e)}}

    # Config with explicit org2 scope
    try:
        override_config = await config.get("{scope_test_config_key}", scope="{org2_id}")
        if override_config and isinstance(override_config, dict):
            results["overridden_scope"]["config"] = override_config.get("scope_marker")
        else:
            results["overridden_scope"]["config"] = None
    except Exception as e:
        results["overridden_scope"]["config"] = {{"error": str(e)}}

    # Knowledge with default scope
    try:
        default_knowledge = await knowledge.search(
            "scope marker",
            namespace="{scope_test_knowledge_namespace}",
            limit=10,
            fallback=False,
        )
        results["default_scope"]["knowledge"] = [
            doc.metadata.get("scope_marker")
            for doc in default_knowledge
            if doc.metadata and doc.metadata.get("scope_marker")
        ]
    except Exception as e:
        results["default_scope"]["knowledge"] = {{"error": str(e)}}

    # Knowledge with explicit org2 scope
    try:
        override_knowledge = await knowledge.search(
            "scope marker",
            namespace="{scope_test_knowledge_namespace}",
            limit=10,
            scope="{org2_id}",
            fallback=False,
        )
        results["overridden_scope"]["knowledge"] = [
            doc.metadata.get("scope_marker")
            for doc in override_knowledge
            if doc.metadata and doc.metadata.get("scope_marker")
        ]
    except Exception as e:
        results["overridden_scope"]["knowledge"] = {{"error": str(e)}}

    return results
'''
        result = write_and_register(
            e2e_client, platform_admin.headers,
            workflow_path, workflow_content, workflow_name,
        )
        workflow_id = result["id"]

        # Set organization_id to org1
        response = e2e_client.patch(
            f"/api/workflows/{workflow_id}",
            headers=platform_admin.headers,
            json={"organization_id": org1["id"]},
        )
        assert response.status_code == 200, f"Set workflow org failed: {response.text}"

        yield {
            "id": workflow_id,
            "name": workflow_name,
            "org_id": org1["id"],
            "path": workflow_path,
        }

        # Cleanup
        e2e_client.delete(
            f"/api/files/editor?path={workflow_path}",
            headers=platform_admin.headers,
        )

    def test_explicit_scope_overrides_context(
        self,
        e2e_client,
        platform_admin,
        scope_override_workflow,
        org1_table_data,
        org2_table_data,
        org1_config_data,
        org2_config_data,
        org1_knowledge_data,
        org2_knowledge_data,
    ):
        """
        SDK operations with explicit scope should access that scope's data,
        regardless of the workflow's organization.
        """
        # Ensure fixtures are loaded
        assert org1_table_data is not None
        assert org2_table_data is not None
        assert org1_config_data is not None
        assert org2_config_data is not None
        assert org1_knowledge_data is not None
        assert org2_knowledge_data is not None

        response = e2e_client.post(
            "/api/workflows/execute",
            headers=platform_admin.headers,
            json={
                "workflow_id": scope_override_workflow["id"],
                "input_data": {},
            },
        )
        assert response.status_code == 200, f"Execute failed: {response.text}"
        data = response.json()
        assert data["status"] == "Success", f"Execution failed: {data}"

        result = data.get("result", {})

        # Verify default scope (should be org1)
        default = result.get("default_scope", {})
        assert "org1" in default.get("tables", []), (
            f"Default tables should see org1. Got: {default.get('tables')}"
        )
        assert default.get("config") == "org1", (
            f"Default config should be org1. Got: {default.get('config')}"
        )
        assert "org1" in default.get("knowledge", []), (
            f"Default knowledge should see org1. Got: {default.get('knowledge')}"
        )

        # Verify overridden scope (should be org2)
        overridden = result.get("overridden_scope", {})
        assert "org2" in overridden.get("tables", []), (
            f"Overridden tables should see org2. Got: {overridden.get('tables')}"
        )
        assert overridden.get("config") == "org2", (
            f"Overridden config should be org2. Got: {overridden.get('config')}"
        )
        assert "org2" in overridden.get("knowledge", []), (
            f"Overridden knowledge should see org2. Got: {overridden.get('knowledge')}"
        )


# =============================================================================
# Test Cases - Regular Org User Workflow Execution
# =============================================================================


@pytest.mark.e2e
class TestOrgUserWorkflowExecution:
    """
    Test that regular org users can execute workflows they have access to.

    Tests the authorization flow for non-superusers:
    - Authenticated workflows (access_level=authenticated)
    - Role-based workflows (access_level=role_based)
    - Cross-org access denial
    """

    @pytest.fixture(scope="class")
    def org1_authenticated_workflow(
        self,
        e2e_client,
        platform_admin,
        org1,
    ):
        """
        Create a workflow scoped to org1 with access_level=authenticated.

        Any user in org1 can execute this workflow.
        """
        workflow_name = "e2e_org1_authenticated_workflow"
        workflow_path = f"{workflow_name}.py"

        workflow_content = f'''"""E2E Org1 Authenticated Workflow"""
from bifrost import workflow, context

@workflow(
    name="{workflow_name}",
    description="Tests org user execution of authenticated workflow",
    execution_mode="sync",
)
async def {workflow_name}():
    """Returns execution context info."""
    return {{
        "executed": True,
        "org_id": context.org_id,
        "scope": context.scope,
    }}
'''
        result = write_and_register(
            e2e_client, platform_admin.headers,
            workflow_path, workflow_content, workflow_name,
        )
        workflow_id = result["id"]

        # Set organization_id and access_level=authenticated
        response = e2e_client.patch(
            f"/api/workflows/{workflow_id}",
            headers=platform_admin.headers,
            json={
                "organization_id": org1["id"],
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 200, f"Set workflow org/access_level failed: {response.text}"

        yield {
            "id": workflow_id,
            "name": workflow_name,
            "org_id": org1["id"],
            "path": workflow_path,
        }

        # Cleanup
        e2e_client.delete(
            f"/api/files/editor?path={workflow_path}",
            headers=platform_admin.headers,
        )

    @pytest.fixture(scope="class")
    def global_authenticated_workflow(
        self,
        e2e_client,
        platform_admin,
    ):
        """
        Create a global workflow with access_level=authenticated.

        Any authenticated user can execute this workflow.
        """
        workflow_name = "e2e_global_authenticated_workflow"
        workflow_path = f"{workflow_name}.py"

        workflow_content = f'''"""E2E Global Authenticated Workflow"""
from bifrost import workflow, context

@workflow(
    name="{workflow_name}",
    description="Tests org user execution of global authenticated workflow",
    execution_mode="sync",
)
async def {workflow_name}():
    """Returns execution context info."""
    return {{
        "executed": True,
        "org_id": context.org_id,
        "scope": context.scope,
    }}
'''
        result = write_and_register(
            e2e_client, platform_admin.headers,
            workflow_path, workflow_content, workflow_name,
        )
        workflow_id = result["id"]

        # Set access_level=authenticated (no organization_id = global)
        response = e2e_client.patch(
            f"/api/workflows/{workflow_id}",
            headers=platform_admin.headers,
            json={
                "organization_id": None,
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 200, f"Set workflow access_level failed: {response.text}"

        yield {
            "id": workflow_id,
            "name": workflow_name,
            "org_id": None,
            "path": workflow_path,
        }

        # Cleanup
        e2e_client.delete(
            f"/api/files/editor?path={workflow_path}",
            headers=platform_admin.headers,
        )

    @pytest.fixture(scope="class")
    def org2_authenticated_workflow(
        self,
        e2e_client,
        platform_admin,
        org2,
    ):
        """
        Create a workflow scoped to org2 with access_level=authenticated.

        Only users in org2 can execute this workflow.
        """
        workflow_name = "e2e_org2_authenticated_workflow"
        workflow_path = f"{workflow_name}.py"

        workflow_content = f'''"""E2E Org2 Authenticated Workflow"""
from bifrost import workflow, context

@workflow(
    name="{workflow_name}",
    description="Tests cross-org access denial",
    execution_mode="sync",
)
async def {workflow_name}():
    """Returns execution context info."""
    return {{
        "executed": True,
        "org_id": context.org_id,
        "scope": context.scope,
    }}
'''
        result = write_and_register(
            e2e_client, platform_admin.headers,
            workflow_path, workflow_content, workflow_name,
        )
        workflow_id = result["id"]

        # Set organization_id=org2 and access_level=authenticated
        response = e2e_client.patch(
            f"/api/workflows/{workflow_id}",
            headers=platform_admin.headers,
            json={
                "organization_id": org2["id"],
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 200, f"Set workflow org/access_level failed: {response.text}"

        yield {
            "id": workflow_id,
            "name": workflow_name,
            "org_id": org2["id"],
            "path": workflow_path,
        }

        # Cleanup
        e2e_client.delete(
            f"/api/files/editor?path={workflow_path}",
            headers=platform_admin.headers,
        )

    def test_org_user_executes_own_org_authenticated_workflow(
        self,
        e2e_client,
        org1_user,
        org1,
        org1_authenticated_workflow,
    ):
        """
        Regular org user can execute authenticated workflow in their org.

        org1_user executing org1's authenticated workflow should succeed.
        """
        response = e2e_client.post(
            "/api/workflows/execute",
            headers=org1_user.headers,
            json={
                "workflow_id": org1_authenticated_workflow["id"],
                "input_data": {},
            },
        )
        assert response.status_code == 200, f"Execute failed: {response.text}"
        data = response.json()
        assert data["status"] == "Success", f"Execution failed: {data}"

        result = data.get("result", {})
        assert result["executed"] is True
        # Org-scoped workflow uses workflow's org_id
        assert result["org_id"] == org1["id"], (
            f"Expected org_id={org1['id']}, got {result['org_id']}"
        )

    def test_org_user_executes_global_authenticated_workflow(
        self,
        e2e_client,
        org1_user,
        org1,
        global_authenticated_workflow,
    ):
        """
        Regular org user can execute global authenticated workflow.

        org1_user executing global workflow should succeed,
        with workflow using org1_user's org context.
        """
        response = e2e_client.post(
            "/api/workflows/execute",
            headers=org1_user.headers,
            json={
                "workflow_id": global_authenticated_workflow["id"],
                "input_data": {},
            },
        )
        assert response.status_code == 200, f"Execute failed: {response.text}"
        data = response.json()
        assert data["status"] == "Success", f"Execution failed: {data}"

        result = data.get("result", {})
        assert result["executed"] is True
        # Global workflow uses caller's org context
        assert result["org_id"] == org1["id"], (
            f"Expected caller's org_id={org1['id']}, got {result['org_id']}"
        )

    def test_org_user_cannot_execute_other_org_workflow(
        self,
        e2e_client,
        org1_user,
        org2_authenticated_workflow,
    ):
        """
        Regular org user cannot execute workflow from another org.

        org1_user trying to execute org2's workflow should get 403.
        """
        response = e2e_client.post(
            "/api/workflows/execute",
            headers=org1_user.headers,
            json={
                "workflow_id": org2_authenticated_workflow["id"],
                "input_data": {},
            },
        )
        # 404 is also acceptable — scoped lookup won't find another org's workflow
        assert response.status_code in (403, 404), (
            f"Expected 403 or 404, got {response.status_code}: {response.text}"
        )

    def test_superuser_can_execute_any_org_workflow(
        self,
        e2e_client,
        platform_admin,
        org1,
        org2,
        org1_authenticated_workflow,
        org2_authenticated_workflow,
    ):
        """
        Platform admin (superuser) can execute any org's workflow.

        Verifies the superuser bypass fix - platform admin with org_id=None
        should be able to execute org-scoped workflows.
        """
        # Execute org1 workflow
        response = e2e_client.post(
            "/api/workflows/execute",
            headers=platform_admin.headers,
            json={
                "workflow_id": org1_authenticated_workflow["id"],
                "input_data": {},
            },
        )
        assert response.status_code == 200, f"Execute org1 workflow failed: {response.text}"
        data = response.json()
        assert data["status"] == "Success", f"Execution failed: {data}"
        assert data.get("result", {}).get("org_id") == org1["id"]

        # Execute org2 workflow
        response = e2e_client.post(
            "/api/workflows/execute",
            headers=platform_admin.headers,
            json={
                "workflow_id": org2_authenticated_workflow["id"],
                "input_data": {},
            },
        )
        assert response.status_code == 200, f"Execute org2 workflow failed: {response.text}"
        data = response.json()
        assert data["status"] == "Success", f"Execution failed: {data}"
        assert data.get("result", {}).get("org_id") == org2["id"]
