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
        warnings = data.get("warnings", [])
        unreg_warnings = [
            w for w in warnings if "unreg_wf" in w.get("detail", "")
        ]
        assert len(unreg_warnings) > 0, (
            f"Expected unregistered function warning, got: {warnings}"
        )

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=workflows/unreg_preflight.py",
            headers=platform_admin.headers,
        )
