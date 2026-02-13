"""E2E tests for on-demand preflight validation."""

import pytest


@pytest.mark.e2e
class TestPreflight:
    """Test POST /api/maintenance/preflight endpoint."""

    def test_preflight_returns_results(self, e2e_client, platform_admin):
        """Preflight endpoint returns validation results."""
        resp = e2e_client.post(
            "/api/maintenance/preflight",
            headers=platform_admin.headers,
        )
        assert resp.status_code == 200, f"Preflight failed: {resp.text}"
        data = resp.json()
        assert "valid" in data
        assert "issues" in data
        assert "warnings" in data

    def test_preflight_detects_unregistered_functions(
        self, e2e_client, platform_admin
    ):
        """Preflight warns about decorated functions that aren't registered."""
        file_content = '''
from bifrost import workflow

@workflow(name="Unregistered WF")
def unreg_wf():
    pass
'''
        # Write file via editor API
        e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "workflows/unreg_preflight.py",
                "content": file_content,
                "encoding": "utf-8",
            },
        )

        resp = e2e_client.post(
            "/api/maintenance/preflight",
            headers=platform_admin.headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Unregistered functions may appear in issues or warnings depending
        # on the endpoint implementation.  Combine both lists and look for
        # entries with the "unregistered_function" category that mention the
        # function name.
        all_items = data.get("issues", []) + data.get("warnings", [])
        unreg_items = [
            item
            for item in all_items
            if item.get("category") == "unregistered_function"
            and "unreg_wf" in item.get("detail", "")
        ]
        assert len(unreg_items) > 0, (
            f"Expected unregistered function issue/warning, got: {all_items}"
        )

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=workflows/unreg_preflight.py",
            headers=platform_admin.headers,
        )
