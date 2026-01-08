"""
Unit tests for entity_detector module.

Tests the entity type detection for platform files including
workflows, data providers, forms, apps, agents, and modules.
"""

from src.services.file_storage.entity_detector import (
    detect_platform_entity_type,
    detect_python_entity_type,
)


class TestDetectPlatformEntityType:
    """Tests for detect_platform_entity_type function."""

    def test_form_json_returns_form(self):
        """Files ending with .form.json are detected as forms."""
        result = detect_platform_entity_type("my_form.form.json", b"{}")
        assert result == "form"

    def test_app_json_returns_app(self):
        """Files ending with .app.json are detected as apps."""
        result = detect_platform_entity_type("my_app.app.json", b"{}")
        assert result == "app"

    def test_agent_json_returns_agent(self):
        """Files ending with .agent.json are detected as agents."""
        result = detect_platform_entity_type("my_agent.agent.json", b"{}")
        assert result == "agent"

    def test_python_file_with_workflow_decorator(self):
        """Python files with @workflow decorator are detected as workflows."""
        code = b"""
from bifrost import workflow

@workflow
def my_workflow():
    pass
"""
        result = detect_platform_entity_type("my_workflow.py", code)
        assert result == "workflow"

    def test_python_file_with_data_provider_decorator(self):
        """Python files with @data_provider decorator are detected as workflows."""
        code = b"""
from bifrost import data_provider

@data_provider
def my_provider():
    return []
"""
        result = detect_platform_entity_type("my_provider.py", code)
        assert result == "workflow"

    def test_python_file_without_decorators_returns_module(self):
        """Python files without SDK decorators are detected as modules."""
        code = b"""
def helper():
    return "helper"
"""
        result = detect_platform_entity_type("utils.py", code)
        assert result == "module"

    def test_non_python_file_returns_none(self):
        """Non-Python files return None (stored in S3)."""
        result = detect_platform_entity_type("data.json", b"{}")
        assert result is None

    def test_regular_json_returns_none(self):
        """Regular JSON files (not .form.json etc) return None."""
        result = detect_platform_entity_type("config.json", b"{}")
        assert result is None

    def test_text_file_returns_none(self):
        """Text files return None (stored in S3)."""
        result = detect_platform_entity_type("readme.txt", b"Hello world")
        assert result is None

    def test_csv_file_returns_none(self):
        """CSV files return None (stored in S3)."""
        result = detect_platform_entity_type("data.csv", b"a,b,c")
        assert result is None


class TestDetectPythonEntityType:
    """Tests for detect_python_entity_type function."""

    def test_workflow_decorator_returns_workflow(self):
        """Files with @workflow decorator return 'workflow'."""
        code = b"""
from bifrost import workflow

@workflow(id="test-id", name="Test")
def my_workflow():
    pass
"""
        result = detect_python_entity_type(code)
        assert result == "workflow"

    def test_workflow_decorator_no_parens_returns_workflow(self):
        """Files with @workflow (no parentheses) return 'workflow'."""
        code = b"""
from bifrost import workflow

@workflow
def my_workflow():
    pass
"""
        result = detect_python_entity_type(code)
        assert result == "workflow"

    def test_data_provider_decorator_returns_workflow(self):
        """Files with @data_provider decorator return 'workflow' (stored in workflows table)."""
        code = b"""
from bifrost import data_provider

@data_provider(id="provider-id", name="Provider")
def my_provider():
    return []
"""
        result = detect_python_entity_type(code)
        assert result == "workflow"

    def test_data_provider_no_parens_returns_workflow(self):
        """Files with @data_provider (no parentheses) return 'workflow'."""
        code = b"""
from bifrost import data_provider

@data_provider
def my_provider():
    return []
"""
        result = detect_python_entity_type(code)
        assert result == "workflow"

    def test_plain_python_returns_module(self):
        """Plain Python files without decorators return 'module'."""
        code = b"""
def helper():
    return "helper"

class MyClass:
    pass
"""
        result = detect_python_entity_type(code)
        assert result == "module"

    def test_empty_python_file_returns_module(self):
        """Empty Python files return 'module'."""
        result = detect_python_entity_type(b"")
        assert result == "module"

    def test_python_with_imports_only_returns_module(self):
        """Python files with just imports return 'module'."""
        code = b"""
import os
import sys
from pathlib import Path
"""
        result = detect_python_entity_type(code)
        assert result == "module"

    def test_workflow_in_comment_returns_module(self):
        """@workflow in comments does not make it a workflow."""
        code = b"""
# This is not a @workflow
def helper():
    pass
"""
        result = detect_python_entity_type(code)
        assert result == "module"

    def test_workflow_in_string_returns_module(self):
        """@workflow in strings does not make it a workflow."""
        code = b'''
def helper():
    return "@workflow is just a string"
'''
        result = detect_python_entity_type(code)
        assert result == "module"

    def test_workflow_as_variable_returns_module(self):
        """workflow as a variable name does not make it a workflow."""
        code = b"""
workflow = "not a decorator"
data_provider = None

def helper():
    pass
"""
        result = detect_python_entity_type(code)
        assert result == "module"

    def test_syntax_error_returns_module(self):
        """Python files with syntax errors return 'module'."""
        code = b"""
def broken(
    # missing closing paren
"""
        result = detect_python_entity_type(code)
        assert result == "module"

    def test_non_utf8_returns_none(self):
        """Non-UTF-8 decodable content returns None."""
        # Invalid UTF-8 sequence
        code = b"\xff\xfe"
        # This should still decode with errors="replace"
        result = detect_python_entity_type(code)
        # After decode with errors="replace", it's still valid but just replacement chars
        assert result == "module"

    def test_async_workflow_returns_workflow(self):
        """Async function with @workflow decorator is detected."""
        code = b"""
from bifrost import workflow

@workflow
async def async_workflow():
    pass
"""
        result = detect_python_entity_type(code)
        assert result == "workflow"

    def test_multiple_decorators_with_workflow(self):
        """Functions with multiple decorators including @workflow are detected."""
        code = b"""
from bifrost import workflow

def other_decorator(f):
    return f

@other_decorator
@workflow
def my_workflow():
    pass
"""
        result = detect_python_entity_type(code)
        assert result == "workflow"

    def test_class_with_method_not_workflow(self):
        """Decorated class methods don't count as workflows (function-level only)."""
        code = b"""
class MyClass:
    @staticmethod
    def method():
        pass
"""
        result = detect_python_entity_type(code)
        assert result == "module"

    def test_utility_module_with_classes_returns_module(self):
        """Utility modules with classes and functions return 'module'."""
        code = b"""
import logging

logger = logging.getLogger(__name__)

class DataProcessor:
    def __init__(self, data):
        self.data = data

    def process(self):
        return self.data.upper()

def format_result(result):
    return f"Result: {result}"
"""
        result = detect_python_entity_type(code)
        assert result == "module"

    def test_init_file_returns_module(self):
        """__init__.py files return 'module'."""
        code = b"""
from .utils import helper
from .models import MyModel

__all__ = ["helper", "MyModel"]
"""
        result = detect_python_entity_type(code)
        assert result == "module"
