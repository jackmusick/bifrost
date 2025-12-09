"""Shared fixtures for repository unit tests"""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_context():
    """Mock ExecutionContext for scoped repositories"""
    context = MagicMock()
    context.org_id = "test-org-123"
    context.user_id = "test-user-456"
    context.scope = "test-org-123"
    context.email = "test@example.com"
    return context


@pytest.fixture
def sample_form_data():
    """Sample form data for testing"""
    return {
        "name": "User Onboarding",
        "description": "Onboard new users",
        "fields": [
            {
                "type": "text",
                "name": "email",
                "label": "Email Address",
                "required": True,
            },
            {"type": "text", "name": "name", "label": "Full Name", "required": True},
        ],
    }


@pytest.fixture
def sample_organization_data():
    """Sample organization data for testing"""
    return {
        "name": "Test Organization",
        "config": {
            "default_license": "O365_E3",
            "welcome_email_template": "welcome_v1",
        },
    }


@pytest.fixture
def sample_user_data():
    """Sample user data for testing"""
    return {
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "password": "SecurePassword123!",
    }


@pytest.fixture
def sample_execution_data():
    """Sample execution data for testing"""
    return {
        "workflow_id": "workflow-123",
        "org_id": "test-org-123",
        "user_id": "test-user-456",
        "input_data": {"key": "value"},
        "status": "PENDING",
    }
