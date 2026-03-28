"""Unit tests for the OpenAPI SDK generator."""

from __future__ import annotations

import inspect
import json


SIMPLE_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Sample API"},
    "paths": {
        "/widgets": {
            "get": {
                "summary": "List widgets",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Widget"},
                                }
                            }
                        }
                    }
                },
            },
            "post": {
                "summary": "Create widget",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Widget"}
                        }
                    }
                },
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Widget"}
                            }
                        }
                    }
                },
            },
        }
    },
    "components": {
        "schemas": {
            "Widget": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                },
            }
        }
    },
}


class TestSDKGenerator:
    """Tests for async SDK generation output."""

    def test_generates_async_httpx_sdk(self):
        """Generated SDKs should use async httpx instead of sync requests."""
        from src.services.sdk_generator import generate_sdk_from_content

        result = generate_sdk_from_content(
            content=json.dumps(SIMPLE_SPEC),
            content_type="json",
            integration_name="Sample Integration",
            auth_type="oauth",
            module_name="sample_api",
        )

        assert "import httpx" in result.code
        assert "import requests" not in result.code
        assert "async def list_widgets" in result.code
        assert "async def create_widgets" in result.code
        assert "await self._request_with_retry" in result.code
        assert "await self.client.request" in result.code
        assert "httpx.AsyncClient" in result.code
        assert "asyncio.to_thread" not in result.code

    def test_generated_client_methods_are_coroutines(self):
        """Generated client methods and lazy wrappers should be awaitable."""
        from src.services.sdk_generator import generate_sdk_from_content

        result = generate_sdk_from_content(
            content=json.dumps(SIMPLE_SPEC),
            content_type="json",
            integration_name="Sample Integration",
            auth_type="oauth",
            module_name="sample_api",
        )

        namespace: dict[str, object] = {}
        exec(result.code, namespace)

        internal_client = namespace["_SampleAPIClient"]
        lazy_client = namespace["_LazyClient"]()

        assert inspect.iscoroutinefunction(internal_client.list_widgets)
        assert inspect.iscoroutinefunction(internal_client.create_widgets)
        assert inspect.iscoroutinefunction(lazy_client.__getattr__("list_widgets"))
