"""
Factory functions for test data.

These replace data-only pytest fixtures with plain functions that support
overrides, making tests more readable and explicit.

Usage:
    from tests.helpers.factories import make_user_data, make_org_data

    def test_something():
        user = make_user_data(email="custom@example.com")
"""

from typing import Any


def make_user_data(**overrides: Any) -> dict[str, Any]:
    """
    Build sample user data dict.

    Defaults match the old ``sample_user_data`` fixture in the root conftest.
    """
    data: dict[str, Any] = {
        "email": "test@example.com",
        "password": "SecurePassword123!",
        "name": "Test User",
    }
    data.update(overrides)
    return data


def make_org_data(**overrides: Any) -> dict[str, Any]:
    """
    Build sample organization data dict.

    Defaults match the old ``sample_org_data`` fixture in the root conftest.
    """
    data: dict[str, Any] = {
        "name": "Test Organization",
        "domain": "example.com",
    }
    data.update(overrides)
    return data


def make_form_data(**overrides: Any) -> dict[str, Any]:
    """
    Build sample form data dict.

    Defaults match the old ``sample_form_data`` fixture in the root conftest.
    """
    data: dict[str, Any] = {
        "name": "User Onboarding",
        "description": "Onboard new users",
        "linkedWorkflow": "user_onboarding",
        "formSchema": {
            "fields": [
                {
                    "type": "text",
                    "name": "email",
                    "label": "Email Address",
                    "required": True,
                },
                {
                    "type": "text",
                    "name": "name",
                    "label": "Full Name",
                    "required": True,
                },
            ]
        },
        "isPublic": False,
    }
    data.update(overrides)
    return data


def make_workflow_data(**overrides: Any) -> dict[str, Any]:
    """
    Build sample workflow data dict.

    Defaults match the old ``sample_workflow_data`` fixture in the root conftest.
    """
    data: dict[str, Any] = {
        "name": "user_onboarding",
        "description": "User onboarding workflow",
        "steps": [
            {
                "id": "step1",
                "name": "Validate Input",
                "action": "validate",
            },
            {
                "id": "step2",
                "name": "Create User",
                "action": "create_user",
            },
        ],
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Factories derived from tests/unit/repositories/conftest.py
# ---------------------------------------------------------------------------


def make_repo_user_data(**overrides: Any) -> dict[str, Any]:
    """
    Build sample user data as used by repository tests.

    Defaults match the old ``sample_user_data`` fixture in the
    repositories conftest (note: has first_name/last_name instead of name).
    """
    data: dict[str, Any] = {
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "password": "SecurePassword123!",
    }
    data.update(overrides)
    return data


def make_repo_form_data(**overrides: Any) -> dict[str, Any]:
    """
    Build sample form data as used by repository tests.

    Defaults match the old ``sample_form_data`` fixture in the
    repositories conftest (note: uses ``fields`` instead of ``formSchema``).
    """
    data: dict[str, Any] = {
        "name": "User Onboarding",
        "description": "Onboard new users",
        "fields": [
            {
                "type": "text",
                "name": "email",
                "label": "Email Address",
                "required": True,
            },
            {
                "type": "text",
                "name": "name",
                "label": "Full Name",
                "required": True,
            },
        ],
    }
    data.update(overrides)
    return data


def make_organization_data(**overrides: Any) -> dict[str, Any]:
    """
    Build sample organization data as used by repository tests.

    Defaults match the old ``sample_organization_data`` fixture in the
    repositories conftest (note: includes ``config`` key).
    """
    data: dict[str, Any] = {
        "name": "Test Organization",
        "config": {
            "default_license": "O365_E3",
            "welcome_email_template": "welcome_v1",
        },
    }
    data.update(overrides)
    return data


def make_execution_data(**overrides: Any) -> dict[str, Any]:
    """
    Build sample execution data as used by repository tests.

    Defaults match the old ``sample_execution_data`` fixture in the
    repositories conftest.
    """
    data: dict[str, Any] = {
        "workflow_id": "workflow-123",
        "org_id": "test-org-123",
        "user_id": "test-user-456",
        "input_data": {"key": "value"},
        "status": "PENDING",
    }
    data.update(overrides)
    return data
