"""
Forms SDK for Bifrost.

Provides Python API for form operations (read-only).

All methods are async and must be awaited.
"""

from __future__ import annotations

import json as json_module
import logging
from typing import Any

from src.core.cache import forms_hash_key, get_redis, user_forms_key

from ._internal import get_context

logger = logging.getLogger(__name__)


class forms:
    """
    Form operations (read-only).

    Allows workflows to list and get form definitions.
    Reads from Redis cache (pre-warmed before execution).

    All methods are async - await is required.
    """

    @staticmethod
    async def list() -> list[dict[str, Any]]:
        """
        List all forms available to the current user.

        Reads from Redis cache (pre-warmed with user's accessible forms).

        Returns:
            list[dict]: List of form dictionaries

        Raises:
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import forms
            >>> all_forms = await forms.list()
            >>> for form in all_forms:
            ...     print(f"{form['id']}: {form['name']}")
        """
        context = get_context()

        org_id = None
        if context.org_id and context.org_id != "GLOBAL":
            org_id = context.org_id

        # Read forms from Redis cache (pre-warmed)
        async with get_redis() as r:
            # Get form IDs accessible to this user
            form_ids = await r.smembers(user_forms_key(org_id, context.user_id))  # type: ignore[misc]

            if not form_ids:
                return []

            # Get form data for each ID
            forms_list: list[dict[str, Any]] = []
            for form_id in form_ids:
                data = await r.hget(forms_hash_key(org_id), form_id)  # type: ignore[misc]
                if data:
                    try:
                        form_data = json_module.loads(data)
                        forms_list.append(form_data)
                    except json_module.JSONDecodeError:
                        continue

            # Sort by name
            forms_list.sort(key=lambda f: f.get("name", ""))

            return forms_list

    @staticmethod
    async def get(form_id: str) -> dict[str, Any]:
        """
        Get a form definition by ID.

        Reads from Redis cache (pre-warmed).

        Args:
            form_id: Form ID

        Returns:
            dict: Form dictionary

        Raises:
            ValueError: If form not found
            PermissionError: If user doesn't have access to the form
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import forms
            >>> form = await forms.get("form-123")
            >>> print(form['name'])
        """
        context = get_context()

        org_id = None
        if context.org_id and context.org_id != "GLOBAL":
            org_id = context.org_id

        # Read from Redis cache (pre-warmed)
        async with get_redis() as r:
            # Check if user has access to this form
            if not context.is_platform_admin:
                form_ids = await r.smembers(user_forms_key(org_id, context.user_id))  # type: ignore[misc]
                if form_id not in form_ids:
                    raise PermissionError(f"Access denied to form: {form_id}")

            # Get form data
            data = await r.hget(forms_hash_key(org_id), form_id)  # type: ignore[misc]

            if not data:
                raise ValueError(f"Form not found: {form_id}")

            try:
                form_data = json_module.loads(data)
                return form_data
            except json_module.JSONDecodeError:
                raise ValueError(f"Invalid form data: {form_id}")
