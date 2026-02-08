"""
Unit tests for entity_detector module.

Tests the entity type detection for platform files including
workflows, data providers, tools, forms, agents, modules, and text files.
"""

import ast

import pytest

from src.services.file_storage.entity_detector import (
    detect_platform_entity_type,
    detect_python_entity_type,
    detect_python_entity_type_with_ast,
)


# ---------------------------------------------------------------------------
# 1. detect_platform_entity_type
# ---------------------------------------------------------------------------


class TestDetectPlatformEntityType:
    """Tests for detect_platform_entity_type function."""

    def test_form_json_returns_form(self):
        result = detect_platform_entity_type("my_form.form.json", b"{}")
        assert result == "form"

    def test_nested_path_form_json_returns_form(self):
        result = detect_platform_entity_type("some/dir/contact.form.json", b"{}")
        assert result == "form"

    def test_agent_json_returns_agent(self):
        result = detect_platform_entity_type("my_agent.agent.json", b"{}")
        assert result == "agent"

    def test_nested_path_agent_json_returns_agent(self):
        result = detect_platform_entity_type("agents/helper.agent.json", b"{}")
        assert result == "agent"

    def test_python_file_delegates_to_python_detector(self):
        """Python files with @workflow decorator are detected as workflows."""
        code = b"from bifrost import workflow\n\n@workflow\ndef my_wf():\n    pass\n"
        result = detect_platform_entity_type("my_workflow.py", code)
        assert result == "workflow"

    def test_python_module_returns_module(self):
        code = b"def helper():\n    return 42\n"
        result = detect_platform_entity_type("utils.py", code)
        assert result == "module"

    @pytest.mark.parametrize(
        "filename",
        [
            "readme.md",
            "notes.txt",
            "docs.rst",
            "config.yaml",
            "settings.yml",
            "pyproject.toml",
            "setup.ini",
            "setup.cfg",
        ],
    )
    def test_text_extensions_return_text(self, filename):
        result = detect_platform_entity_type(filename, b"some content")
        assert result == "text"

    @pytest.mark.parametrize(
        "filename",
        [
            "data.csv",
            "image.png",
            "archive.zip",
            "data.json",
            "config.json",
            "my_app.app.json",
            "binary.exe",
            "spreadsheet.xlsx",
        ],
    )
    def test_unknown_extensions_return_none(self, filename):
        result = detect_platform_entity_type(filename, b"content")
        assert result is None

    def test_form_json_takes_precedence_over_json(self):
        """'.form.json' is detected as form, not as a generic json (None)."""
        result = detect_platform_entity_type("x.form.json", b"{}")
        assert result == "form"

    def test_agent_json_takes_precedence_over_json(self):
        result = detect_platform_entity_type("x.agent.json", b"{}")
        assert result == "agent"


# ---------------------------------------------------------------------------
# 2. detect_python_entity_type
# ---------------------------------------------------------------------------


class TestDetectPythonEntityType:
    """Tests for detect_python_entity_type -- returns just the entity_type string."""

    def test_workflow_decorator_returns_workflow(self):
        code = b"@workflow\ndef my_wf():\n    pass\n"
        assert detect_python_entity_type(code) == "workflow"

    def test_workflow_with_args_returns_workflow(self):
        code = b'@workflow(name="Test")\ndef my_wf():\n    pass\n'
        assert detect_python_entity_type(code) == "workflow"

    def test_data_provider_returns_workflow(self):
        code = b"@data_provider\ndef my_dp():\n    return []\n"
        assert detect_python_entity_type(code) == "workflow"

    def test_data_provider_with_args_returns_workflow(self):
        code = b'@data_provider(name="DP")\ndef my_dp():\n    return []\n'
        assert detect_python_entity_type(code) == "workflow"

    def test_tool_decorator_returns_workflow(self):
        code = b"@tool\ndef my_tool():\n    pass\n"
        assert detect_python_entity_type(code) == "workflow"

    def test_tool_with_args_returns_workflow(self):
        code = b'@tool(name="My Tool")\ndef my_tool():\n    pass\n'
        assert detect_python_entity_type(code) == "workflow"

    def test_plain_module_returns_module(self):
        code = b"def helper():\n    return 42\n"
        assert detect_python_entity_type(code) == "module"

    def test_empty_file_returns_module(self):
        assert detect_python_entity_type(b"") == "module"

    def test_imports_only_returns_module(self):
        code = b"import os\nimport sys\nfrom pathlib import Path\n"
        assert detect_python_entity_type(code) == "module"

    def test_async_workflow_returns_workflow(self):
        code = b"@workflow\nasync def async_wf():\n    pass\n"
        assert detect_python_entity_type(code) == "workflow"

    def test_multiple_decorators_with_workflow(self):
        code = b"def deco(f):\n    return f\n\n@deco\n@workflow\ndef wf():\n    pass\n"
        assert detect_python_entity_type(code) == "workflow"


# ---------------------------------------------------------------------------
# 3. detect_python_entity_type_with_ast (full result checks)
# ---------------------------------------------------------------------------


class TestDetectPythonEntityTypeWithAst:
    """Tests for detect_python_entity_type_with_ast -- full PythonEntityDetectionResult."""

    # --- Basic workflow detection with result object checks ---

    def test_workflow_result_fields(self):
        code = b"@workflow\ndef wf():\n    pass\n"
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "workflow"
        assert result.ast_tree is not None
        assert result.content_str is not None
        assert result.has_decorators is True
        assert result.syntax_error is None

    def test_module_without_decorators_skips_ast(self):
        """Plain modules skip AST parsing entirely for performance."""
        code = b"x = 1\n"
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "module"
        assert result.ast_tree is None  # AST not parsed
        assert result.content_str == "x = 1\n"
        assert result.has_decorators is False
        assert result.syntax_error is None

    def test_data_provider_result(self):
        code = b"@data_provider\ndef dp():\n    return []\n"
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "workflow"
        assert result.has_decorators is True
        assert result.ast_tree is not None

    def test_tool_result(self):
        code = b"@tool\ndef t():\n    pass\n"
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "workflow"
        assert result.has_decorators is True

    # --- Syntax errors ---

    def test_syntax_error_returns_module_with_error_info(self):
        code = b"@workflow\ndef broken(\n"
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "module"
        assert result.ast_tree is None
        assert result.has_decorators is True  # Pattern was found
        assert result.syntax_error is not None
        assert len(result.syntax_error) > 0

    def test_syntax_error_preserves_content_str(self):
        code = b"@workflow\ndef broken(\n"
        result = detect_python_entity_type_with_ast(code)
        assert result.content_str is not None
        assert "@workflow" in result.content_str

    # --- False positives: decorator text in comments / strings ---

    def test_workflow_in_comment_returns_module(self):
        code = b"# This is not a @workflow\ndef helper():\n    pass\n"
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "module"
        # AST is parsed because the fast string check finds "@workflow"
        assert result.ast_tree is not None
        assert result.has_decorators is False

    def test_workflow_in_string_returns_module(self):
        code = b'def helper():\n    return "@workflow is just text"\n'
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "module"
        assert result.ast_tree is not None
        assert result.has_decorators is False

    def test_data_provider_in_docstring_returns_module(self):
        code = b'def helper():\n    """Uses @data_provider pattern."""\n    pass\n'
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "module"
        assert result.has_decorators is False

    def test_tool_in_variable_name_returns_module(self):
        """'@tool' appears in content but not as an actual decorator."""
        code = b'# @tool usage example\ntool = "not a decorator"\n'
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "module"
        assert result.has_decorators is False

    # --- Async functions ---

    def test_async_function_with_workflow(self):
        code = b"@workflow\nasync def async_wf():\n    await something()\n"
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "workflow"
        assert result.has_decorators is True

    def test_async_function_with_data_provider(self):
        code = b"@data_provider\nasync def async_dp():\n    return []\n"
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "workflow"

    # --- Decorator with arguments ---

    def test_workflow_with_name_arg(self):
        code = b'@workflow(name="My Workflow")\ndef wf():\n    pass\n'
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "workflow"
        assert result.has_decorators is True

    def test_workflow_with_multiple_args(self):
        code = b'@workflow(name="WF", description="A workflow", version=2)\ndef wf():\n    pass\n'
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "workflow"

    def test_data_provider_with_args(self):
        code = b'@data_provider(name="DP", cache_ttl=300)\ndef dp():\n    return []\n'
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "workflow"

    # --- Attribute access pattern (e.g. bifrost.workflow) ---
    # NOTE: The fast string check looks for "@workflow", "@data_provider", "@tool"
    # as substrings. "@bifrost.workflow" does NOT contain "@workflow" (the @ is
    # before "bifrost", not "workflow"), so the fast path returns "module" without
    # AST parsing.  The _parse_decorator function handles attribute access, but
    # it is only reached when the content passes the fast check.

    def test_bifrost_dot_workflow_without_fast_match_returns_module(self):
        """@bifrost.workflow alone does NOT pass the fast string check."""
        code = b'@bifrost.workflow(name="test")\ndef wf():\n    pass\n'
        result = detect_python_entity_type_with_ast(code)
        # Fast check: "@workflow" not in content_str -> True -> returns module
        assert result.entity_type == "module"
        assert result.ast_tree is None
        assert result.has_decorators is False

    def test_bifrost_dot_workflow_with_fast_match_in_comment(self):
        """When '@workflow' also appears as a substring (e.g. in a comment),
        the fast check passes and _parse_decorator's attribute handling
        detects the actual @bifrost.workflow decorator."""
        code = b'# See @workflow docs\n@bifrost.workflow(name="test")\ndef wf():\n    pass\n'
        result = detect_python_entity_type_with_ast(code)
        # "@workflow" IS in content (in the comment), so AST is parsed
        # _parse_decorator handles the attribute access pattern
        assert result.entity_type == "workflow"
        assert result.has_decorators is True

    def test_bifrost_dot_data_provider_without_fast_match_returns_module(self):
        code = b"@bifrost.data_provider()\ndef dp():\n    return []\n"
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "module"

    def test_bifrost_dot_tool_without_fast_match_returns_module(self):
        code = b"@bifrost.tool()\ndef t():\n    pass\n"
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "module"

    # --- Non-matching decorators ---

    def test_unrelated_decorator_returns_module(self):
        """A decorator that is not workflow/data_provider/tool is ignored."""
        code = b"@some_other_decorator\ndef f():\n    pass\n"
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "module"
        assert result.has_decorators is False  # No pattern match at all

    def test_staticmethod_decorator_returns_module(self):
        code = b"class C:\n    @staticmethod\n    def method():\n        pass\n"
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "module"

    # --- Edge: non-decodable content ---

    def test_content_with_replacement_chars(self):
        """bytes.decode with errors='replace' still produces a string -- result is module."""
        code = b"\xff\xfe"
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "module"
        assert result.content_str is not None

    # --- Multiple functions, first one without decorator ---

    def test_second_function_has_workflow(self):
        code = b"def helper():\n    pass\n\n@workflow\ndef wf():\n    pass\n"
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "workflow"

    def test_class_method_with_workflow_decorator(self):
        """@workflow on a method inside a class body should still be detected
        because ast.walk visits nested FunctionDef nodes."""
        code = b"class C:\n    @workflow\n    def method(self):\n        pass\n"
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "workflow"


# ---------------------------------------------------------------------------
# 4. _parse_decorator -- tested via AST parsing of code snippets
# ---------------------------------------------------------------------------


class TestParseDecorator:
    """Test _parse_decorator indirectly through AST parsing and detect_python_entity_type_with_ast.

    Since _parse_decorator is a private function, we test it by constructing
    Python code with specific decorator patterns and observing the detection result.
    We also parse AST directly for fine-grained assertions about the kwargs extraction.
    """

    @staticmethod
    def _get_first_decorator_info(code_str: str):
        """Helper: parse code, find first function, call _parse_decorator on first decorator."""
        from src.services.file_storage.entity_detector import _parse_decorator

        tree = ast.parse(code_str)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.decorator_list:
                    return _parse_decorator(node.decorator_list[0])
        return None

    # --- ast.Name nodes (bare @workflow) ---

    def test_name_workflow(self):
        info = self._get_first_decorator_info("@workflow\ndef f(): pass")
        assert info is not None
        name, kwargs = info
        assert name == "workflow"
        assert kwargs == {}

    def test_name_tool(self):
        info = self._get_first_decorator_info("@tool\ndef f(): pass")
        assert info is not None
        name, kwargs = info
        assert name == "tool"
        assert kwargs == {}

    def test_name_data_provider(self):
        info = self._get_first_decorator_info("@data_provider\ndef f(): pass")
        assert info is not None
        name, kwargs = info
        assert name == "data_provider"
        assert kwargs == {}

    def test_name_unrelated_decorator_returns_none(self):
        info = self._get_first_decorator_info("@some_deco\ndef f(): pass")
        assert info is None

    # --- ast.Call nodes (@workflow(...)) ---

    def test_call_workflow_no_args(self):
        info = self._get_first_decorator_info("@workflow()\ndef f(): pass")
        assert info is not None
        name, kwargs = info
        assert name == "workflow"
        assert kwargs == {}

    def test_call_workflow_with_kwargs(self):
        info = self._get_first_decorator_info('@workflow(name="My WF", version=3)\ndef f(): pass')
        assert info is not None
        name, kwargs = info
        assert name == "workflow"
        assert kwargs == {"name": "My WF", "version": 3}

    def test_call_data_provider_with_kwargs(self):
        info = self._get_first_decorator_info('@data_provider(name="DP")\ndef f(): pass')
        assert info is not None
        name, kwargs = info
        assert name == "data_provider"
        assert kwargs == {"name": "DP"}

    def test_call_tool_with_kwargs(self):
        info = self._get_first_decorator_info('@tool(name="T", enabled=True)\ndef f(): pass')
        assert info is not None
        name, kwargs = info
        assert name == "tool"
        assert kwargs["name"] == "T"
        assert kwargs["enabled"] is True

    def test_call_unrelated_decorator_returns_none(self):
        info = self._get_first_decorator_info("@other_thing(x=1)\ndef f(): pass")
        assert info is None

    # --- Attribute access (@bifrost.workflow) ---

    def test_attribute_workflow_call(self):
        info = self._get_first_decorator_info('@bifrost.workflow(name="test")\ndef f(): pass')
        assert info is not None
        name, kwargs = info
        assert name == "workflow"
        assert kwargs == {"name": "test"}

    def test_attribute_data_provider_call(self):
        info = self._get_first_decorator_info("@bifrost.data_provider()\ndef f(): pass")
        assert info is not None
        name, kwargs = info
        assert name == "data_provider"
        assert kwargs == {}

    def test_attribute_unrelated_returns_none(self):
        info = self._get_first_decorator_info("@bifrost.something_else()\ndef f(): pass")
        assert info is None

    # --- Keyword with None arg (e.g. **kwargs expansion) ---

    def test_call_with_starstar_kwargs_ignored(self):
        """Double-star kwargs in decorator calls have keyword.arg == None and are skipped."""
        info = self._get_first_decorator_info("@workflow(**config)\ndef f(): pass")
        assert info is not None
        name, kwargs = info
        assert name == "workflow"
        assert kwargs == {}  # **config is skipped


# ---------------------------------------------------------------------------
# 5. _ast_value_to_python
# ---------------------------------------------------------------------------


class TestAstValueToPython:
    """Test _ast_value_to_python via AST nodes parsed from real Python expressions."""

    @staticmethod
    def _eval_ast_value(expr_str: str):
        """Helper: parse a Python expression string and convert its AST node."""
        from src.services.file_storage.entity_detector import _ast_value_to_python

        tree = ast.parse(expr_str, mode="eval")
        return _ast_value_to_python(tree.body)

    # --- Constants ---

    def test_string_constant(self):
        assert self._eval_ast_value('"hello"') == "hello"

    def test_int_constant(self):
        assert self._eval_ast_value("42") == 42

    def test_float_constant(self):
        assert self._eval_ast_value("3.14") == 3.14

    def test_true_constant(self):
        assert self._eval_ast_value("True") is True

    def test_false_constant(self):
        assert self._eval_ast_value("False") is False

    def test_none_constant(self):
        assert self._eval_ast_value("None") is None

    # --- Lists ---

    def test_empty_list(self):
        assert self._eval_ast_value("[]") == []

    def test_list_of_ints(self):
        assert self._eval_ast_value("[1, 2, 3]") == [1, 2, 3]

    def test_list_of_strings(self):
        assert self._eval_ast_value('["a", "b"]') == ["a", "b"]

    def test_nested_list(self):
        assert self._eval_ast_value("[[1, 2], [3]]") == [[1, 2], [3]]

    # --- Dicts ---

    def test_empty_dict(self):
        assert self._eval_ast_value("{}") == {}

    def test_dict_with_string_keys(self):
        result = self._eval_ast_value('{"key": "value", "num": 5}')
        assert result == {"key": "value", "num": 5}

    def test_dict_with_int_keys(self):
        result = self._eval_ast_value("{1: 'a', 2: 'b'}")
        assert result == {1: "a", 2: "b"}

    def test_dict_with_bool_values(self):
        result = self._eval_ast_value('{"enabled": True, "disabled": False}')
        assert result == {"enabled": True, "disabled": False}

    # --- Unresolvable expressions return None ---

    def test_name_reference_returns_none(self):
        """A bare variable name (not True/False/None) returns None."""
        assert self._eval_ast_value("some_variable") is None

    def test_function_call_returns_none(self):
        """A function call expression returns None (not a simple constant)."""
        assert self._eval_ast_value("int('5')") is None

    # --- Mixed structures ---

    def test_list_with_none(self):
        assert self._eval_ast_value("[1, None, 3]") == [1, None, 3]

    def test_dict_with_list_value(self):
        result = self._eval_ast_value('{"items": [1, 2, 3]}')
        assert result == {"items": [1, 2, 3]}

    def test_negative_number(self):
        """Negative numbers are represented as UnaryOp in the AST, so they
        fall through to the default None return."""
        result = self._eval_ast_value("-1")
        # ast.parse("-1") produces UnaryOp(USub, Constant(1)) which is not
        # handled by _ast_value_to_python -- returns None
        assert result is None


# ---------------------------------------------------------------------------
# Integration-style: full end-to-end snippets
# ---------------------------------------------------------------------------


class TestEndToEndSnippets:
    """Realistic code snippets that exercise multiple layers together."""

    def test_realistic_workflow_file(self):
        code = b"""\
from bifrost import workflow
from bifrost.context import Context

@workflow(name="Onboard Client", description="Onboard a new client")
async def onboard_client(ctx: Context):
    client_name = ctx.params.get("client_name")
    await ctx.log(f"Onboarding {client_name}")
    return {"status": "ok"}
"""
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "workflow"
        assert result.has_decorators is True
        assert result.ast_tree is not None
        assert result.syntax_error is None

    def test_realistic_data_provider_file(self):
        code = b"""\
from bifrost import data_provider

@data_provider(name="Client List")
def get_clients():
    return [
        {"id": 1, "name": "Acme Corp"},
        {"id": 2, "name": "Globex"},
    ]
"""
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "workflow"
        assert result.has_decorators is True

    def test_realistic_module_file(self):
        code = b"""\
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class DateHelper:
    @staticmethod
    def format_date(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d")

def parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")
"""
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "module"
        assert result.has_decorators is False
        # No decorator patterns found -- AST is not parsed
        assert result.ast_tree is None

    def test_file_with_workflow_in_docstring_only(self):
        code = b"""\
\"\"\"
This module documents @workflow usage patterns.
It does NOT contain an actual workflow.
\"\"\"

def explain():
    return "See @workflow docs"
"""
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "module"
        # Fast check finds "@workflow" so AST is parsed
        assert result.ast_tree is not None
        assert result.has_decorators is False

    def test_multiple_workflows_in_one_file(self):
        code = b"""\
from bifrost import workflow

@workflow(name="First")
def first():
    pass

@workflow(name="Second")
def second():
    pass
"""
        result = detect_python_entity_type_with_ast(code)
        # Detection returns on the first match
        assert result.entity_type == "workflow"
        assert result.has_decorators is True

    def test_workflow_and_tool_mixed(self):
        code = b"""\
from bifrost import workflow, tool

@tool(name="Helper Tool")
def helper():
    pass

@workflow(name="Main")
def main():
    pass
"""
        result = detect_python_entity_type_with_ast(code)
        assert result.entity_type == "workflow"
        assert result.has_decorators is True

    def test_platform_entity_type_for_markdown(self):
        assert detect_platform_entity_type("README.md", b"# Hello") == "text"

    def test_platform_entity_type_for_yaml(self):
        assert detect_platform_entity_type("config.yaml", b"key: value") == "text"

    def test_platform_entity_type_for_unknown_binary(self):
        assert detect_platform_entity_type("image.png", b"\x89PNG") is None
