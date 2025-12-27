"""
Chat E2E Tests.

Tests chat conversation and message operations.
Requires LLM configuration to be set for message sending tests.
"""

import logging

import pytest

logger = logging.getLogger(__name__)


# =============================================================================
# Conversation CRUD Tests
# =============================================================================


class TestConversationsCRUD:
    """Test conversation CRUD operations."""

    def test_create_conversation(
        self,
        e2e_client,
        platform_admin,
        test_chat_agent,
    ):
        """Test creating a conversation with an agent."""
        response = e2e_client.post(
            "/api/chat/conversations",
            json={
                "agent_id": test_chat_agent["id"],
                "channel": "chat",
                "title": "Test Conversation",
            },
            headers=platform_admin.headers,
        )
        assert response.status_code == 201, f"Create conversation failed: {response.text}"

        data = response.json()
        assert data["agent_id"] == test_chat_agent["id"]
        assert data["channel"] == "chat"
        assert data["title"] == "Test Conversation"
        assert data["is_active"] is True
        assert data["message_count"] == 0
        assert "id" in data

    def test_create_conversation_with_nonexistent_agent(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test creating a conversation with nonexistent agent returns 404."""
        import uuid
        fake_agent_id = str(uuid.uuid4())

        response = e2e_client.post(
            "/api/chat/conversations",
            json={
                "agent_id": fake_agent_id,
                "channel": "chat",
            },
            headers=platform_admin.headers,
        )
        assert response.status_code == 404

    def test_list_conversations_empty(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test listing conversations when none exist."""
        response = e2e_client.get(
            "/api/chat/conversations",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_conversations(
        self,
        e2e_client,
        platform_admin,
        test_conversation,
    ):
        """Test listing user's conversations."""
        response = e2e_client.get(
            "/api/chat/conversations",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        # Should include the test conversation
        conv_ids = [c["id"] for c in data]
        assert test_conversation["id"] in conv_ids

    def test_get_conversation(
        self,
        e2e_client,
        platform_admin,
        test_conversation,
    ):
        """Test getting a conversation by ID."""
        response = e2e_client.get(
            f"/api/chat/conversations/{test_conversation['id']}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == test_conversation["id"]
        assert data["agent_name"] is not None

    def test_get_conversation_not_found(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test getting nonexistent conversation returns 404."""
        import uuid
        fake_id = str(uuid.uuid4())

        response = e2e_client.get(
            f"/api/chat/conversations/{fake_id}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 404

    def test_delete_conversation(
        self,
        e2e_client,
        platform_admin,
        test_conversation,
    ):
        """Test soft deleting a conversation."""
        response = e2e_client.delete(
            f"/api/chat/conversations/{test_conversation['id']}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 204

        # Verify it's not listed by default (inactive)
        response = e2e_client.get(
            "/api/chat/conversations",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        conv_ids = [c["id"] for c in response.json()]
        assert test_conversation["id"] not in conv_ids


# =============================================================================
# Conversation Access Control Tests
# =============================================================================


class TestConversationsAccessControl:
    """Test conversation access control."""

    def test_user_can_only_see_own_conversations(
        self,
        e2e_client,
        platform_admin,
        org1_user,
        test_chat_agent,
    ):
        """Test that users can only see their own conversations."""
        # Create conversation as platform admin
        response = e2e_client.post(
            "/api/chat/conversations",
            json={
                "agent_id": test_chat_agent["id"],
                "channel": "chat",
            },
            headers=platform_admin.headers,
        )
        assert response.status_code == 201
        admin_conv_id = response.json()["id"]

        # Org user should not see admin's conversation
        response = e2e_client.get(
            "/api/chat/conversations",
            headers=org1_user.headers,
        )
        assert response.status_code == 200
        conv_ids = [c["id"] for c in response.json()]
        assert admin_conv_id not in conv_ids

        # Clean up
        e2e_client.delete(
            f"/api/chat/conversations/{admin_conv_id}",
            headers=platform_admin.headers,
        )

    def test_user_cannot_access_other_users_conversation(
        self,
        e2e_client,
        platform_admin,
        org1_user,
        test_conversation,
    ):
        """Test that users cannot access other users' conversations."""
        response = e2e_client.get(
            f"/api/chat/conversations/{test_conversation['id']}",
            headers=org1_user.headers,
        )
        assert response.status_code == 404

    def test_user_cannot_delete_other_users_conversation(
        self,
        e2e_client,
        org1_user,
        test_conversation,
    ):
        """Test that users cannot delete other users' conversations."""
        response = e2e_client.delete(
            f"/api/chat/conversations/{test_conversation['id']}",
            headers=org1_user.headers,
        )
        assert response.status_code == 404


# =============================================================================
# Message Tests
# =============================================================================


class TestMessages:
    """Test message operations."""

    def test_get_messages_empty(
        self,
        e2e_client,
        platform_admin,
        test_conversation,
    ):
        """Test getting messages from empty conversation."""
        response = e2e_client.get(
            f"/api/chat/conversations/{test_conversation['id']}/messages",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_get_messages_from_nonexistent_conversation(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test getting messages from nonexistent conversation returns 404."""
        import uuid
        fake_id = str(uuid.uuid4())

        response = e2e_client.get(
            f"/api/chat/conversations/{fake_id}/messages",
            headers=platform_admin.headers,
        )
        assert response.status_code == 404

    def test_send_message_without_llm_config(
        self,
        e2e_client,
        platform_admin,
        test_conversation,
        llm_config_cleanup,
    ):
        """Test sending message fails gracefully without LLM config."""
        response = e2e_client.post(
            f"/api/chat/conversations/{test_conversation['id']}/messages",
            json={"message": "Hello, agent!"},
            headers=platform_admin.headers,
        )
        # Should fail with 500 because LLM is not configured
        assert response.status_code == 500

    def test_send_message_to_nonexistent_conversation(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test sending message to nonexistent conversation returns 404."""
        import uuid
        fake_id = str(uuid.uuid4())

        response = e2e_client.post(
            f"/api/chat/conversations/{fake_id}/messages",
            json={"message": "Hello!"},
            headers=platform_admin.headers,
        )
        assert response.status_code == 404


class TestMessagesWithLLM:
    """Test message operations that require LLM configuration."""

    def test_send_message_and_get_response(
        self,
        e2e_client,
        platform_admin,
        test_conversation,
        llm_anthropic_configured,
    ):
        """Test sending a message and receiving a response."""
        import time

        # Retry logic for transient API errors (rate limiting, overloaded, etc.)
        max_retries = 3
        for attempt in range(max_retries):
            response = e2e_client.post(
                f"/api/chat/conversations/{test_conversation['id']}/messages",
                json={"message": "Say 'Hello Test' and nothing else."},
                headers=platform_admin.headers,
                timeout=30.0,  # LLM calls can take a few seconds
            )

            if response.status_code == 200:
                break
            elif response.status_code == 500:
                error_text = response.text.lower()
                if "overloaded" in error_text or "rate" in error_text:
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
            # For other errors, fail immediately
            break

        assert response.status_code == 200, f"Send message failed: {response.text}"

        data = response.json()
        assert "content" in data
        assert "message_id" in data
        # The response should contain something
        assert len(data["content"]) > 0

    def test_messages_are_persisted(
        self,
        e2e_client,
        platform_admin,
        test_conversation,
        llm_anthropic_configured,
    ):
        """Test that messages are persisted after sending."""
        import time

        # Retry logic for transient API errors (rate limiting, overloaded, etc.)
        max_retries = 3
        for attempt in range(max_retries):
            # Send a message
            response = e2e_client.post(
                f"/api/chat/conversations/{test_conversation['id']}/messages",
                json={"message": "Reply with the word 'test' only."},
                headers=platform_admin.headers,
                timeout=30.0,
            )

            if response.status_code == 200:
                break
            elif response.status_code == 500:
                error_text = response.text.lower()
                if "overloaded" in error_text or "rate" in error_text:
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
            # For other errors, fail immediately
            break

        assert response.status_code == 200

        # Get messages - should have user message and assistant response
        response = e2e_client.get(
            f"/api/chat/conversations/{test_conversation['id']}/messages",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        messages = response.json()
        assert len(messages) >= 2  # At least user message + assistant response

        # Find user and assistant messages
        roles = [m["role"] for m in messages]
        assert "user" in roles
        assert "assistant" in roles


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def test_chat_agent(e2e_client, platform_admin):
    """Create a test agent for chat tests."""
    response = e2e_client.post(
        "/api/agents",
        json={
            "name": "E2E Chat Test Agent",
            "description": "Agent for chat E2E testing",
            "system_prompt": "You are a helpful test assistant. Keep your responses brief.",
            "channels": ["chat"],
            "access_level": "authenticated",
        },
        headers=platform_admin.headers,
    )
    assert response.status_code == 201, f"Failed to create test agent: {response.text}"
    agent = response.json()

    yield agent

    # Cleanup - delete the agent
    try:
        e2e_client.delete(
            f"/api/agents/{agent['id']}",
            headers=platform_admin.headers,
        )
    except Exception:
        pass


@pytest.fixture
def test_conversation(e2e_client, platform_admin, test_chat_agent):
    """Create a test conversation for use in tests."""
    response = e2e_client.post(
        "/api/chat/conversations",
        json={
            "agent_id": test_chat_agent["id"],
            "channel": "chat",
            "title": "E2E Test Conversation",
        },
        headers=platform_admin.headers,
    )
    assert response.status_code == 201, f"Failed to create test conversation: {response.text}"
    conversation = response.json()

    yield conversation

    # Cleanup - delete the conversation
    try:
        e2e_client.delete(
            f"/api/chat/conversations/{conversation['id']}",
            headers=platform_admin.headers,
        )
    except Exception:
        pass
