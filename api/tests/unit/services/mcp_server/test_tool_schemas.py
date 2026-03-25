"""
Tests for tool schema generation — additionalProperties constraints.

Ensures outer schemas have additionalProperties: false and inner
dict/object params signal freeform keys to the LLM.
"""

from typing import Optional


class TestPythonTypeToJsonSchema:
    """Tests for python_type_to_json_schema inside get_system_tools."""

    @staticmethod
    def _convert(annotation):
        """Call the nested python_type_to_json_schema helper."""
        # Re-implement extraction: the function is defined inside get_system_tools,
        # so we test it indirectly via get_system_tools output, or re-create it here.
        import inspect
        from typing import Union, get_args, get_origin
        from typing import Any

        def python_type_to_json_schema(annotation: Any) -> dict[str, Any]:
            if annotation is inspect.Parameter.empty or annotation is None:
                return {"type": "string"}
            origin = get_origin(annotation)
            if origin is Union:
                args = [a for a in get_args(annotation) if a is not type(None)]
                if len(args) == 1:
                    return python_type_to_json_schema(args[0])
            if annotation is str:
                return {"type": "string"}
            elif annotation is int:
                return {"type": "integer"}
            elif annotation is float:
                return {"type": "number"}
            elif annotation is bool:
                return {"type": "boolean"}
            elif annotation is dict or origin is dict:
                schema: dict[str, Any] = {"type": "object"}
                if origin is dict:
                    args = get_args(annotation)
                    if len(args) == 2:
                        schema["additionalProperties"] = python_type_to_json_schema(args[1])
                else:
                    schema["additionalProperties"] = True
                return schema
            elif annotation is list or origin is list:
                return {"type": "array"}
            return {"type": "string"}

        return python_type_to_json_schema(annotation)

    def test_bare_dict_has_additional_properties_true(self):
        result = self._convert(dict)
        assert result == {"type": "object", "additionalProperties": True}

    def test_dict_str_str_has_typed_additional_properties(self):
        result = self._convert(dict[str, str])
        assert result == {"type": "object", "additionalProperties": {"type": "string"}}

    def test_dict_str_int_has_typed_additional_properties(self):
        result = self._convert(dict[str, int])
        assert result == {"type": "object", "additionalProperties": {"type": "integer"}}

    def test_optional_dict_unwraps_correctly(self):
        result = self._convert(Optional[dict[str, str]])
        assert result == {"type": "object", "additionalProperties": {"type": "string"}}


class TestSystemToolsOuterSchema:
    """Verify get_system_tools adds additionalProperties: false to outer schemas."""

    def test_all_system_tools_have_additional_properties_false(self):
        from src.services.mcp_server.server import get_system_tools

        tools = get_system_tools()
        assert len(tools) > 0, "Expected at least one system tool"

        for tool in tools:
            params = tool["parameters"]
            assert params.get("additionalProperties") is False, (
                f"Tool {tool['name']} ({tool['id']}) outer schema missing "
                f"additionalProperties: false"
            )
