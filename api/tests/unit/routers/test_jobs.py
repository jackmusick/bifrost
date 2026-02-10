"""Tests for job status endpoint with preview data."""
from src.routers.jobs import JobStatusResponse


class TestJobStatusResponse:
    """Test that JobStatusResponse includes preview data."""

    def test_response_includes_preview_field(self):
        """JobStatusResponse should accept a preview dict."""
        response = JobStatusResponse(
            status="success",
            preview={
                "to_pull": [{"path": "workflows/billing.py", "action": "add"}],
                "to_push": [],
                "conflicts": [{
                    "path": "workflows/shared.py",
                    "display_name": "shared",
                    "entity_type": "workflow",
                }],
                "preflight": {"valid": True, "issues": []},
                "is_empty": False,
            },
        )
        assert response.status == "success"
        assert response.preview is not None
        assert len(response.preview["to_pull"]) == 1
        assert len(response.preview["conflicts"]) == 1

    def test_response_preview_defaults_to_none(self):
        """Preview should default to None for non-preview jobs."""
        response = JobStatusResponse(status="pending")
        assert response.preview is None
