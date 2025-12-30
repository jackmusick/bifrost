"""
E2E tests for the Event System.

Tests the full event lifecycle:
- Event Source CRUD (webhook type)
- Event Subscriptions
- Webhook receiver (public endpoint, no auth)
- Event delivery tracking
- Delivery retry
"""

import time
import uuid

import pytest


# Simple test workflow content for subscriptions
TEST_WORKFLOW_CONTENT = '''"""E2E Events Test Workflow"""
from bifrost import workflow

@workflow(
    name="e2e_events_test_workflow",
    description="Test workflow for event subscription E2E tests",
)
async def e2e_events_test_workflow(event: dict) -> dict:
    """Receives event data and returns it."""
    return {
        "status": "received",
        "event_type": event.get("event_type"),
        "data": event.get("data"),
    }
'''


def _wait_for_workflow(e2e_client, platform_admin, workflow_name: str, max_attempts: int = 30) -> dict | None:
    """Wait for a workflow to be discovered and return it."""
    for _ in range(max_attempts):
        response = e2e_client.get(
            "/api/workflows",
            headers=platform_admin.headers,
        )
        if response.status_code == 200:
            workflows = response.json()
            workflow = next(
                (w for w in workflows if w.get("name") == workflow_name),
                None
            )
            if workflow:
                return workflow
        time.sleep(1)
    return None


@pytest.fixture(scope="module")
def test_workflow(e2e_client, platform_admin):
    """
    Create a test workflow file for event subscriptions.

    Creates the workflow via Editor API, waits for discovery,
    and cleans up after tests.
    """
    # Create workflow file with index=true for synchronous discovery
    response = e2e_client.put(
        "/api/files/editor/content?index=true",
        headers=platform_admin.headers,
        json={
            "path": "e2e_events_test_workflow.py",
            "content": TEST_WORKFLOW_CONTENT,
            "encoding": "utf-8",
        },
    )
    assert response.status_code == 200, f"Failed to create workflow file: {response.text}"

    # Wait for workflow discovery
    workflow = _wait_for_workflow(e2e_client, platform_admin, "e2e_events_test_workflow")
    assert workflow is not None, "Workflow e2e_events_test_workflow not discovered after 30s"

    yield workflow

    # Cleanup: delete the workflow file
    e2e_client.delete(
        "/api/files/editor?path=e2e_events_test_workflow.py",
        headers=platform_admin.headers,
    )


@pytest.fixture
def event_source(e2e_client, platform_admin):
    """Create a test event source with webhook config."""
    source_name = f"E2E Test Webhook {uuid.uuid4().hex[:8]}"

    response = e2e_client.post(
        "/api/events/sources",
        headers=platform_admin.headers,
        json={
            "name": source_name,
            "source_type": "webhook",
            "webhook": {
                "adapter_name": "generic",
                "config": {},
            },
        },
    )
    assert response.status_code == 201, f"Failed to create event source: {response.text}"
    source = response.json()

    yield source

    # Cleanup: soft delete the event source
    e2e_client.delete(
        f"/api/events/sources/{source['id']}",
        headers=platform_admin.headers,
    )


@pytest.fixture
def org_event_source(e2e_client, platform_admin, org1):
    """Create an event source scoped to org1."""
    source_name = f"E2E Org Webhook {uuid.uuid4().hex[:8]}"

    response = e2e_client.post(
        "/api/events/sources",
        headers=platform_admin.headers,
        json={
            "name": source_name,
            "source_type": "webhook",
            "organization_id": org1["id"],
            "webhook": {
                "adapter_name": "generic",
                "config": {},
            },
        },
    )
    assert response.status_code == 201, f"Failed to create org event source: {response.text}"
    source = response.json()

    yield source

    # Cleanup
    e2e_client.delete(
        f"/api/events/sources/{source['id']}",
        headers=platform_admin.headers,
    )


@pytest.fixture
def subscription(e2e_client, platform_admin, event_source, test_workflow):
    """Create a subscription linking event source to workflow."""
    response = e2e_client.post(
        f"/api/events/sources/{event_source['id']}/subscriptions",
        headers=platform_admin.headers,
        json={
            "workflow_id": test_workflow["id"],
            "event_type": None,  # Match all events
        },
    )
    assert response.status_code == 201, f"Failed to create subscription: {response.text}"
    sub = response.json()

    yield sub

    # Cleanup handled by event_source deletion (cascade)


# =============================================================================
# TestEventSourceCRUD - Event Source Management
# =============================================================================


@pytest.mark.e2e
class TestEventSourceCRUD:
    """Test event source CRUD operations."""

    def test_list_adapters(self, e2e_client, platform_admin):
        """List available webhook adapters."""
        response = e2e_client.get(
            "/api/events/adapters",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List adapters failed: {response.text}"
        data = response.json()
        assert "adapters" in data
        # Should have at least the generic adapter
        adapter_names = [a["name"] for a in data["adapters"]]
        assert "generic" in adapter_names

    def test_create_webhook_source(self, e2e_client, platform_admin):
        """Platform admin creates webhook event source."""
        source_name = f"E2E Create Test {uuid.uuid4().hex[:8]}"

        response = e2e_client.post(
            "/api/events/sources",
            headers=platform_admin.headers,
            json={
                "name": source_name,
                "source_type": "webhook",
                "webhook": {
                    "adapter_name": "generic",
                    "config": {},
                },
            },
        )
        assert response.status_code == 201, f"Create source failed: {response.text}"

        source = response.json()
        assert source["name"] == source_name
        assert source["source_type"] == "webhook"
        assert source["is_active"] is True
        assert source["webhook"] is not None

        # Cleanup
        e2e_client.delete(
            f"/api/events/sources/{source['id']}",
            headers=platform_admin.headers,
        )

    def test_create_webhook_source_returns_callback_url(self, e2e_client, platform_admin):
        """Verify callback URL is /api/hooks/{uuid}."""
        source_name = f"E2E Callback URL Test {uuid.uuid4().hex[:8]}"

        response = e2e_client.post(
            "/api/events/sources",
            headers=platform_admin.headers,
            json={
                "name": source_name,
                "source_type": "webhook",
                "webhook": {
                    "adapter_name": "generic",
                    "config": {},
                },
            },
        )
        assert response.status_code == 201

        source = response.json()
        callback_url = source["webhook"]["callback_url"]

        # Should be /api/hooks/{source_id}
        assert callback_url == f"/api/hooks/{source['id']}"

        # Cleanup
        e2e_client.delete(
            f"/api/events/sources/{source['id']}",
            headers=platform_admin.headers,
        )

    def test_list_event_sources(self, e2e_client, platform_admin, event_source):
        """List event sources (platform admin sees all)."""
        response = e2e_client.get(
            "/api/events/sources",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List sources failed: {response.text}"

        data = response.json()
        assert "items" in data
        assert "total" in data

        # Should find our test source
        source_ids = [s["id"] for s in data["items"]]
        assert event_source["id"] in source_ids

    def test_get_event_source(self, e2e_client, platform_admin, event_source):
        """Get event source by ID."""
        response = e2e_client.get(
            f"/api/events/sources/{event_source['id']}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"Get source failed: {response.text}"

        source = response.json()
        assert source["id"] == event_source["id"]
        assert source["name"] == event_source["name"]

    def test_update_event_source(self, e2e_client, platform_admin, event_source):
        """Update event source name/status."""
        new_name = f"Updated {uuid.uuid4().hex[:8]}"

        response = e2e_client.patch(
            f"/api/events/sources/{event_source['id']}",
            headers=platform_admin.headers,
            json={
                "name": new_name,
            },
        )
        assert response.status_code == 200, f"Update source failed: {response.text}"

        source = response.json()
        assert source["name"] == new_name

    def test_delete_event_source(self, e2e_client, platform_admin):
        """Soft delete (deactivate) event source."""
        # Create a source to delete
        response = e2e_client.post(
            "/api/events/sources",
            headers=platform_admin.headers,
            json={
                "name": f"To Delete {uuid.uuid4().hex[:8]}",
                "source_type": "webhook",
                "webhook": {"adapter_name": "generic", "config": {}},
            },
        )
        source = response.json()

        # Delete it
        response = e2e_client.delete(
            f"/api/events/sources/{source['id']}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 204, f"Delete failed: {response.text}"

        # Verify it's deactivated (not hard deleted)
        response = e2e_client.get(
            f"/api/events/sources/{source['id']}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_org_user_cannot_create_source(self, e2e_client, org1_user):
        """Only platform admin can create sources."""
        response = e2e_client.post(
            "/api/events/sources",
            headers=org1_user.headers,
            json={
                "name": "Should Fail",
                "source_type": "webhook",
                "webhook": {"adapter_name": "generic", "config": {}},
            },
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"

    def test_org_user_sees_global_sources(self, e2e_client, platform_admin, org1_user, event_source):
        """Org users can see global (non-org-scoped) sources."""
        response = e2e_client.get(
            "/api/events/sources",
            headers=org1_user.headers,
        )
        assert response.status_code == 200, f"List sources failed: {response.text}"

        data = response.json()
        source_ids = [s["id"] for s in data["items"]]

        # Should see global source (event_source has no organization_id)
        assert event_source["id"] in source_ids

    def test_org_user_cannot_see_other_org_sources(
        self, e2e_client, platform_admin, org1_user, org2
    ):
        """Org isolation for org-scoped sources."""
        # Create a source scoped to org2
        response = e2e_client.post(
            "/api/events/sources",
            headers=platform_admin.headers,
            json={
                "name": f"Org2 Source {uuid.uuid4().hex[:8]}",
                "source_type": "webhook",
                "organization_id": org2["id"],
                "webhook": {"adapter_name": "generic", "config": {}},
            },
        )
        org2_source = response.json()

        try:
            # org1_user should NOT see org2's source
            response = e2e_client.get(
                "/api/events/sources",
                headers=org1_user.headers,
            )
            assert response.status_code == 200

            data = response.json()
            source_ids = [s["id"] for s in data["items"]]
            assert org2_source["id"] not in source_ids

            # Direct access should be forbidden
            response = e2e_client.get(
                f"/api/events/sources/{org2_source['id']}",
                headers=org1_user.headers,
            )
            assert response.status_code == 403
        finally:
            # Cleanup
            e2e_client.delete(
                f"/api/events/sources/{org2_source['id']}",
                headers=platform_admin.headers,
            )


# =============================================================================
# TestEventSubscriptions - Subscription Management
# =============================================================================


@pytest.mark.e2e
class TestEventSubscriptions:
    """Test event subscription operations."""

    def test_create_subscription(
        self, e2e_client, platform_admin, event_source, test_workflow
    ):
        """Create workflow subscription to event source."""
        response = e2e_client.post(
            f"/api/events/sources/{event_source['id']}/subscriptions",
            headers=platform_admin.headers,
            json={
                "workflow_id": test_workflow["id"],
                "event_type": "test.event",
            },
        )
        assert response.status_code == 201, f"Create subscription failed: {response.text}"

        sub = response.json()
        assert sub["workflow_id"] == test_workflow["id"]
        assert sub["event_type"] == "test.event"
        assert sub["is_active"] is True

    def test_list_subscriptions(
        self, e2e_client, platform_admin, event_source, subscription
    ):
        """List subscriptions for an event source."""
        response = e2e_client.get(
            f"/api/events/sources/{event_source['id']}/subscriptions",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List subscriptions failed: {response.text}"

        data = response.json()
        assert "items" in data
        sub_ids = [s["id"] for s in data["items"]]
        assert subscription["id"] in sub_ids

    def test_update_subscription(
        self, e2e_client, platform_admin, event_source, subscription
    ):
        """Update event_type filter, is_active."""
        response = e2e_client.patch(
            f"/api/events/sources/{event_source['id']}/subscriptions/{subscription['id']}",
            headers=platform_admin.headers,
            json={
                "event_type": "updated.event",
                "is_active": False,
            },
        )
        assert response.status_code == 200, f"Update subscription failed: {response.text}"

        sub = response.json()
        assert sub["event_type"] == "updated.event"
        assert sub["is_active"] is False

    def test_delete_subscription(
        self, e2e_client, platform_admin, event_source, test_workflow
    ):
        """Soft delete subscription."""
        # Create a subscription to delete
        response = e2e_client.post(
            f"/api/events/sources/{event_source['id']}/subscriptions",
            headers=platform_admin.headers,
            json={"workflow_id": test_workflow["id"]},
        )
        sub = response.json()

        # Delete it
        response = e2e_client.delete(
            f"/api/events/sources/{event_source['id']}/subscriptions/{sub['id']}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 204, f"Delete subscription failed: {response.text}"


# =============================================================================
# TestWebhookReceiver - Webhook Delivery (PUBLIC ENDPOINT)
# =============================================================================


@pytest.mark.e2e
class TestWebhookReceiver:
    """Test webhook receiver endpoint (public, no auth required)."""

    def test_webhook_returns_202(self, e2e_client, event_source):
        """POST to /api/hooks/{source_id} returns 202."""
        source_id = event_source["id"]

        # No auth headers - public endpoint
        response = e2e_client.post(
            f"/api/hooks/{source_id}",
            json={"test": "data"},
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 202, f"Expected 202, got {response.status_code}: {response.text}"
        assert response.text == "Accepted"

    def test_webhook_creates_event(self, e2e_client, platform_admin, event_source):
        """Webhook POST creates Event record."""
        source_id = event_source["id"]

        # Send webhook
        e2e_client.post(
            f"/api/hooks/{source_id}",
            json={"action": "test.created", "data": {"key": "value"}},
        )

        # Wait a moment for async processing
        time.sleep(0.5)

        # Verify event was created
        response = e2e_client.get(
            f"/api/events/sources/{source_id}/events",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        events = response.json()["items"]
        assert len(events) >= 1

        # Find our event
        matching_events = [
            e for e in events
            if e.get("data", {}).get("action") == "test.created"
        ]
        assert len(matching_events) >= 1

    def test_webhook_with_invalid_source_returns_404(self, e2e_client):
        """Invalid UUID returns 404."""
        fake_uuid = str(uuid.uuid4())

        response = e2e_client.post(
            f"/api/hooks/{fake_uuid}",
            json={"test": "data"},
        )

        assert response.status_code == 404

    def test_webhook_with_inactive_source_returns_404(
        self, e2e_client, platform_admin
    ):
        """Inactive source returns 404."""
        # Create and immediately deactivate a source
        response = e2e_client.post(
            "/api/events/sources",
            headers=platform_admin.headers,
            json={
                "name": f"Inactive Source {uuid.uuid4().hex[:8]}",
                "source_type": "webhook",
                "webhook": {"adapter_name": "generic", "config": {}},
            },
        )
        source = response.json()

        # Deactivate it
        e2e_client.delete(
            f"/api/events/sources/{source['id']}",
            headers=platform_admin.headers,
        )

        # Try to send webhook
        response = e2e_client.post(
            f"/api/hooks/{source['id']}",
            json={"test": "data"},
        )

        assert response.status_code == 404

    def test_webhook_supports_get_method(self, e2e_client, event_source):
        """GET method for validation challenges."""
        source_id = event_source["id"]

        response = e2e_client.get(f"/api/hooks/{source_id}")

        # GET should be accepted (for validation callbacks like Graph API)
        assert response.status_code == 202

    def test_webhook_supports_json_body(self, e2e_client, platform_admin, event_source):
        """JSON body is parsed and stored."""
        source_id = event_source["id"]

        payload = {
            "event_type": "user.created",
            "user": {
                "id": 123,
                "email": "test@example.com",
            },
        }

        e2e_client.post(
            f"/api/hooks/{source_id}",
            json=payload,
        )

        time.sleep(0.5)

        # Verify payload was stored
        response = e2e_client.get(
            f"/api/events/sources/{source_id}/events",
            headers=platform_admin.headers,
        )
        events = response.json()["items"]

        matching = [
            e for e in events
            if e.get("data", {}).get("event_type") == "user.created"
        ]
        assert len(matching) >= 1
        assert matching[0]["data"]["user"]["email"] == "test@example.com"

    def test_webhook_stores_headers(self, e2e_client, platform_admin, event_source):
        """Request headers are stored in event."""
        source_id = event_source["id"]

        e2e_client.post(
            f"/api/hooks/{source_id}",
            json={"header_test": True},
            headers={
                "X-Custom-Header": "test-value",
                "Content-Type": "application/json",
            },
        )

        time.sleep(0.5)

        response = e2e_client.get(
            f"/api/events/sources/{source_id}/events",
            headers=platform_admin.headers,
        )
        events = response.json()["items"]

        matching = [
            e for e in events
            if e.get("data", {}).get("header_test") is True
        ]
        assert len(matching) >= 1
        # Headers should be stored (lowercase)
        assert "x-custom-header" in matching[0].get("headers", {})

    def test_health_endpoint(self, e2e_client):
        """/api/hooks/health returns 200 OK."""
        response = e2e_client.get("/api/hooks/health")

        assert response.status_code == 200
        assert response.text == "OK"


# =============================================================================
# TestEventDelivery - Event to Workflow Execution
# =============================================================================


@pytest.mark.e2e
class TestEventDelivery:
    """Test event delivery to workflows."""

    def test_event_creates_delivery_for_subscription(
        self, e2e_client, platform_admin, event_source, subscription
    ):
        """Event with matching subscription creates EventDelivery."""
        source_id = event_source["id"]

        # Send webhook
        e2e_client.post(
            f"/api/hooks/{source_id}",
            json={"delivery_test": True},
        )

        time.sleep(1)  # Wait for processing

        # Get events and find our event
        response = e2e_client.get(
            f"/api/events/sources/{source_id}/events",
            headers=platform_admin.headers,
        )
        events = response.json()["items"]

        matching = [
            e for e in events
            if e.get("data", {}).get("delivery_test") is True
        ]
        assert len(matching) >= 1
        event = matching[0]

        # Check deliveries were created
        response = e2e_client.get(
            f"/api/events/{event['id']}/deliveries",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        deliveries = response.json()["items"]
        assert len(deliveries) >= 1
        assert deliveries[0]["workflow_id"] == subscription["workflow_id"]

    def test_event_type_filter_matches(
        self, e2e_client, platform_admin, event_source, test_workflow
    ):
        """Subscription with event_type filter only receives matching events."""
        source_id = event_source["id"]

        # Create subscription with specific event_type filter
        response = e2e_client.post(
            f"/api/events/sources/{source_id}/subscriptions",
            headers=platform_admin.headers,
            json={
                "workflow_id": test_workflow["id"],
                "event_type": "specific.event",
            },
        )
        filtered_sub = response.json()

        # Send non-matching event
        e2e_client.post(
            f"/api/hooks/{source_id}",
            json={"filter_test": "non_matching"},
        )

        time.sleep(0.5)

        # Get the event
        response = e2e_client.get(
            f"/api/events/sources/{source_id}/events",
            headers=platform_admin.headers,
        )
        events = response.json()["items"]
        matching = [
            e for e in events
            if e.get("data", {}).get("filter_test") == "non_matching"
        ]
        assert len(matching) >= 1
        event = matching[0]

        # Should have no deliveries for filtered subscription
        # (since event_type doesn't match "specific.event")
        response = e2e_client.get(
            f"/api/events/{event['id']}/deliveries",
            headers=platform_admin.headers,
        )
        deliveries = response.json()["items"]

        # None of the deliveries should be for filtered_sub
        filtered_deliveries = [
            d for d in deliveries
            if d["event_subscription_id"] == filtered_sub["id"]
        ]
        assert len(filtered_deliveries) == 0

    def test_list_events(self, e2e_client, platform_admin, event_source):
        """List events for an event source."""
        source_id = event_source["id"]

        # Send a few webhooks
        for i in range(3):
            e2e_client.post(
                f"/api/hooks/{source_id}",
                json={"list_test": True, "index": i},
            )

        time.sleep(0.5)

        response = e2e_client.get(
            f"/api/events/sources/{source_id}/events",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert "total" in data

        list_events = [
            e for e in data["items"]
            if e.get("data", {}).get("list_test") is True
        ]
        assert len(list_events) >= 3

    def test_get_event(self, e2e_client, platform_admin, event_source):
        """Get event by ID with delivery counts."""
        source_id = event_source["id"]

        # Send webhook
        e2e_client.post(
            f"/api/hooks/{source_id}",
            json={"get_event_test": True},
        )

        time.sleep(0.5)

        # Get events list
        response = e2e_client.get(
            f"/api/events/sources/{source_id}/events",
            headers=platform_admin.headers,
        )
        events = response.json()["items"]
        matching = [
            e for e in events
            if e.get("data", {}).get("get_event_test") is True
        ]
        assert len(matching) >= 1
        event_id = matching[0]["id"]

        # Get single event
        response = e2e_client.get(
            f"/api/events/{event_id}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        event = response.json()
        assert event["id"] == event_id
        assert "delivery_count" in event
        assert "success_count" in event
        assert "failed_count" in event

    def test_list_deliveries(
        self, e2e_client, platform_admin, event_source, subscription
    ):
        """List deliveries for an event."""
        source_id = event_source["id"]

        # Send webhook
        e2e_client.post(
            f"/api/hooks/{source_id}",
            json={"deliveries_list_test": True},
        )

        time.sleep(1)

        # Get events
        response = e2e_client.get(
            f"/api/events/sources/{source_id}/events",
            headers=platform_admin.headers,
        )
        events = response.json()["items"]
        matching = [
            e for e in events
            if e.get("data", {}).get("deliveries_list_test") is True
        ]
        assert len(matching) >= 1
        event_id = matching[0]["id"]

        # List deliveries
        response = e2e_client.get(
            f"/api/events/{event_id}/deliveries",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert len(data["items"]) >= 1

        delivery = data["items"][0]
        assert "id" in delivery
        assert "status" in delivery
        assert "workflow_id" in delivery


# =============================================================================
# TestDeliveryRetry - Retry Failed Deliveries
# =============================================================================


@pytest.mark.e2e
class TestDeliveryRetry:
    """Test delivery retry functionality."""

    def test_cannot_retry_pending_delivery(
        self, e2e_client, platform_admin, event_source, subscription
    ):
        """Cannot retry a delivery that's not failed."""
        source_id = event_source["id"]

        # Send webhook
        e2e_client.post(
            f"/api/hooks/{source_id}",
            json={"retry_test": True},
        )

        time.sleep(1)

        # Get events and delivery
        response = e2e_client.get(
            f"/api/events/sources/{source_id}/events",
            headers=platform_admin.headers,
        )
        events = response.json()["items"]
        matching = [
            e for e in events
            if e.get("data", {}).get("retry_test") is True
        ]
        event = matching[0]

        response = e2e_client.get(
            f"/api/events/{event['id']}/deliveries",
            headers=platform_admin.headers,
        )
        deliveries = response.json()["items"]

        if not deliveries:
            pytest.skip("No deliveries created")

        delivery = deliveries[0]

        # Try to retry non-failed delivery
        if delivery["status"] not in ["failed", "skipped"]:
            response = e2e_client.post(
                f"/api/events/deliveries/{delivery['id']}/retry",
                headers=platform_admin.headers,
            )
            assert response.status_code == 400, f"Expected 400 for non-failed delivery: {response.text}"
