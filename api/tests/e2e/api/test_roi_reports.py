"""
E2E tests for ROI Reports API.

Tests ROI reporting endpoints for platform administrators.
"""

import pytest
from datetime import date, timedelta


@pytest.mark.e2e
class TestROIReports:
    """Test ROI reporting endpoints."""

    @pytest.fixture
    def test_date_range(self):
        """Provide a test date range."""
        today = date.today()
        return {
            "start_date": (today - timedelta(days=7)).isoformat(),
            "end_date": today.isoformat(),
        }

    def test_get_roi_summary_requires_platform_admin(
        self, e2e_client, org1_user, test_date_range
    ):
        """Non-superuser should get 403 when accessing ROI summary."""
        response = e2e_client.get(
            "/api/reports/roi/summary",
            headers=org1_user.headers,
            params=test_date_range,
        )
        assert response.status_code == 403

    def test_get_roi_summary_success(
        self, e2e_client, platform_admin, test_date_range
    ):
        """Platform admin can get ROI summary."""
        response = e2e_client.get(
            "/api/reports/roi/summary",
            headers=platform_admin.headers,
            params=test_date_range,
        )
        assert response.status_code == 200, f"Get summary failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "start_date" in data
        assert "end_date" in data
        assert "total_executions" in data
        assert "successful_executions" in data
        assert "total_time_saved" in data
        assert "total_value" in data
        assert "time_saved_unit" in data
        assert "value_unit" in data

        # Verify types
        assert isinstance(data["total_executions"], int)
        assert isinstance(data["successful_executions"], int)
        assert isinstance(data["total_time_saved"], int)
        assert isinstance(data["total_value"], (int, float))

        # Verify default units
        assert data["time_saved_unit"] == "minutes"
        assert data["value_unit"] == "USD"

    def test_get_roi_summary_with_org_filter(
        self, e2e_client, platform_admin, org1, test_date_range
    ):
        """Platform admin can filter ROI summary by organization."""
        response = e2e_client.get(
            "/api/reports/roi/summary",
            headers=platform_admin.headers,
            params={
                **test_date_range,
                "organization_id": org1["id"],
            },
        )
        assert response.status_code == 200, f"Get summary failed: {response.text}"
        data = response.json()

        assert "total_executions" in data
        assert isinstance(data["total_executions"], int)

    def test_get_roi_summary_with_invalid_org_header(
        self, e2e_client, platform_admin, test_date_range
    ):
        """Invalid X-Organization-Id header should return 400."""
        # Create headers with invalid organization ID
        headers = platform_admin.headers.copy()
        headers["X-Organization-Id"] = "invalid-uuid-format"

        response = e2e_client.get(
            "/api/reports/roi/summary",
            headers=headers,
            params=test_date_range,
        )
        # Should return 400 or 422 for invalid UUID format
        assert response.status_code in [400, 422]

    def test_get_roi_by_workflow_requires_platform_admin(
        self, e2e_client, org1_user, test_date_range
    ):
        """Non-superuser should get 403 when accessing workflow ROI."""
        response = e2e_client.get(
            "/api/reports/roi/by-workflow",
            headers=org1_user.headers,
            params=test_date_range,
        )
        assert response.status_code == 403

    def test_get_roi_by_workflow_success(
        self, e2e_client, platform_admin, test_date_range
    ):
        """Platform admin can get workflow breakdown of ROI."""
        response = e2e_client.get(
            "/api/reports/roi/by-workflow",
            headers=platform_admin.headers,
            params=test_date_range,
        )
        assert response.status_code == 200, f"Get by workflow failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "workflows" in data
        assert "total_workflows" in data
        assert "time_saved_unit" in data
        assert "value_unit" in data

        assert isinstance(data["workflows"], list)
        assert isinstance(data["total_workflows"], int)
        assert data["total_workflows"] == len(data["workflows"])

        # If there are workflows, verify their structure
        if data["workflows"]:
            workflow = data["workflows"][0]
            assert "workflow_id" in workflow
            assert "workflow_name" in workflow
            assert "execution_count" in workflow
            assert "success_count" in workflow
            assert "time_saved_per_execution" in workflow
            assert "value_per_execution" in workflow
            assert "total_time_saved" in workflow
            assert "total_value" in workflow

    def test_get_roi_by_workflow_with_limit(
        self, e2e_client, platform_admin, test_date_range
    ):
        """Platform admin can limit number of workflows returned."""
        response = e2e_client.get(
            "/api/reports/roi/by-workflow",
            headers=platform_admin.headers,
            params={
                **test_date_range,
                "limit": 5,
            },
        )
        assert response.status_code == 200, f"Get by workflow failed: {response.text}"
        data = response.json()

        # Should return at most 5 workflows
        assert len(data["workflows"]) <= 5

    def test_get_roi_by_workflow_with_org_filter(
        self, e2e_client, platform_admin, org1, test_date_range
    ):
        """Platform admin can filter workflow ROI by organization."""
        response = e2e_client.get(
            "/api/reports/roi/by-workflow",
            headers=platform_admin.headers,
            params={
                **test_date_range,
                "organization_id": org1["id"],
            },
        )
        assert response.status_code == 200, f"Get by workflow failed: {response.text}"
        data = response.json()

        assert "workflows" in data
        assert isinstance(data["workflows"], list)

    def test_get_roi_by_organization_requires_platform_admin(
        self, e2e_client, org1_user, test_date_range
    ):
        """Non-superuser should get 403 when accessing org ROI."""
        response = e2e_client.get(
            "/api/reports/roi/by-organization",
            headers=org1_user.headers,
            params=test_date_range,
        )
        assert response.status_code == 403

    def test_get_roi_by_organization_success(
        self, e2e_client, platform_admin, test_date_range
    ):
        """Platform admin can get organization breakdown of ROI."""
        response = e2e_client.get(
            "/api/reports/roi/by-organization",
            headers=platform_admin.headers,
            params=test_date_range,
        )
        assert (
            response.status_code == 200
        ), f"Get by organization failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "organizations" in data
        assert "time_saved_unit" in data
        assert "value_unit" in data

        assert isinstance(data["organizations"], list)

        # If there are organizations, verify their structure
        if data["organizations"]:
            org = data["organizations"][0]
            assert "organization_id" in org
            assert "organization_name" in org
            assert "execution_count" in org
            assert "success_count" in org
            assert "total_time_saved" in org
            assert "total_value" in org

            # Verify org ID format
            assert org["organization_id"].startswith("ORG:")

    def test_get_roi_by_organization_with_limit(
        self, e2e_client, platform_admin, test_date_range
    ):
        """Platform admin can limit number of organizations returned."""
        response = e2e_client.get(
            "/api/reports/roi/by-organization",
            headers=platform_admin.headers,
            params={
                **test_date_range,
                "limit": 10,
            },
        )
        assert (
            response.status_code == 200
        ), f"Get by organization failed: {response.text}"
        data = response.json()

        # Should return at most 10 organizations
        assert len(data["organizations"]) <= 10

    def test_get_roi_trends_requires_platform_admin(
        self, e2e_client, org1_user, test_date_range
    ):
        """Non-superuser should get 403 when accessing ROI trends."""
        response = e2e_client.get(
            "/api/reports/roi/trends",
            headers=org1_user.headers,
            params=test_date_range,
        )
        assert response.status_code == 403

    def test_get_roi_trends_success_daily(
        self, e2e_client, platform_admin, test_date_range
    ):
        """Platform admin can get daily ROI trends."""
        response = e2e_client.get(
            "/api/reports/roi/trends",
            headers=platform_admin.headers,
            params={
                **test_date_range,
                "granularity": "day",
            },
        )
        assert response.status_code == 200, f"Get trends failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "entries" in data
        assert "granularity" in data
        assert "time_saved_unit" in data
        assert "value_unit" in data

        assert isinstance(data["entries"], list)
        assert data["granularity"] == "day"

        # If there are entries, verify their structure
        if data["entries"]:
            entry = data["entries"][0]
            assert "period" in entry
            assert "execution_count" in entry
            assert "success_count" in entry
            assert "time_saved" in entry
            assert "value" in entry

    def test_get_roi_trends_success_weekly(
        self, e2e_client, platform_admin, test_date_range
    ):
        """Platform admin can get weekly ROI trends."""
        response = e2e_client.get(
            "/api/reports/roi/trends",
            headers=platform_admin.headers,
            params={
                **test_date_range,
                "granularity": "week",
            },
        )
        assert response.status_code == 200, f"Get trends failed: {response.text}"
        data = response.json()

        assert data["granularity"] == "week"
        assert isinstance(data["entries"], list)

    def test_get_roi_trends_success_monthly(
        self, e2e_client, platform_admin, test_date_range
    ):
        """Platform admin can get monthly ROI trends."""
        response = e2e_client.get(
            "/api/reports/roi/trends",
            headers=platform_admin.headers,
            params={
                **test_date_range,
                "granularity": "month",
            },
        )
        assert response.status_code == 200, f"Get trends failed: {response.text}"
        data = response.json()

        assert data["granularity"] == "month"
        assert isinstance(data["entries"], list)

    def test_get_roi_trends_with_org_filter(
        self, e2e_client, platform_admin, org1, test_date_range
    ):
        """Platform admin can filter ROI trends by organization."""
        response = e2e_client.get(
            "/api/reports/roi/trends",
            headers=platform_admin.headers,
            params={
                **test_date_range,
                "organization_id": org1["id"],
                "granularity": "day",
            },
        )
        assert response.status_code == 200, f"Get trends failed: {response.text}"
        data = response.json()

        assert "entries" in data
        assert isinstance(data["entries"], list)

    def test_get_roi_trends_invalid_granularity(
        self, e2e_client, platform_admin, test_date_range
    ):
        """Invalid granularity should return 422."""
        response = e2e_client.get(
            "/api/reports/roi/trends",
            headers=platform_admin.headers,
            params={
                **test_date_range,
                "granularity": "invalid",
            },
        )
        assert response.status_code == 422


@pytest.mark.e2e
class TestROISettings:
    """Test ROI settings endpoints."""

    def test_get_roi_settings_requires_platform_admin(
        self, e2e_client, org1_user
    ):
        """Non-superuser should get 403 when accessing ROI settings."""
        response = e2e_client.get(
            "/api/admin/roi/settings",
            headers=org1_user.headers,
        )
        assert response.status_code == 403

    def test_get_roi_settings_returns_defaults(
        self, e2e_client, platform_admin
    ):
        """Platform admin can get ROI settings (defaults)."""
        response = e2e_client.get(
            "/api/admin/roi/settings",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"Get settings failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "time_saved_unit" in data
        assert "value_unit" in data

        # Should have defaults
        assert data["time_saved_unit"] == "minutes"
        assert data["value_unit"] == "USD"

    def test_update_roi_settings_requires_platform_admin(
        self, e2e_client, org1_user
    ):
        """Non-superuser should get 403 when updating ROI settings."""
        response = e2e_client.post(
            "/api/admin/roi/settings",
            headers=org1_user.headers,
            json={
                "time_saved_unit": "hours",
                "value_unit": "EUR",
            },
        )
        assert response.status_code == 403

    def test_update_roi_settings_success(self, e2e_client, platform_admin):
        """Platform admin can update ROI settings."""
        # Update settings
        response = e2e_client.post(
            "/api/admin/roi/settings",
            headers=platform_admin.headers,
            json={
                "time_saved_unit": "hours",
                "value_unit": "GBP",
            },
        )
        assert response.status_code == 200, f"Update settings failed: {response.text}"
        data = response.json()

        # Verify updated values
        assert data["time_saved_unit"] == "hours"
        assert data["value_unit"] == "GBP"

        # Verify settings persist by fetching again
        response = e2e_client.get(
            "/api/admin/roi/settings",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["time_saved_unit"] == "hours"
        assert data["value_unit"] == "GBP"

        # Reset to defaults for other tests
        e2e_client.post(
            "/api/admin/roi/settings",
            headers=platform_admin.headers,
            json={
                "time_saved_unit": "minutes",
                "value_unit": "USD",
            },
        )
