"""Tests for code_surgery.remove_function_from_source."""

import pytest

from src.services.file_storage.code_surgery import remove_function_from_source


class TestRemoveFunctionFromSource:
    """Tests for removing a function block from Python source."""

    def test_single_function_returns_none(self):
        """If the function is the only top-level function, return None (delete file)."""
        source = '''from bifrost import workflow

@workflow(name="test")
def my_workflow(param: str):
    """Do something."""
    return {"result": param}
'''
        result = remove_function_from_source(source, "my_workflow")
        assert result is None

    def test_remove_first_of_two_functions(self):
        """Remove the first function, keep the second."""
        source = '''from bifrost import workflow

@workflow(name="first")
def first_workflow(param: str):
    """First workflow."""
    return {"result": param}


@workflow(name="second")
def second_workflow(param: str):
    """Second workflow."""
    return {"result": param}
'''
        result = remove_function_from_source(source, "first_workflow")
        assert result is not None
        assert "first_workflow" not in result
        assert "second_workflow" in result
        assert "@workflow" in result
        assert "from bifrost import workflow" in result

    def test_remove_second_of_two_functions(self):
        """Remove the second function, keep the first."""
        source = '''from bifrost import workflow

@workflow(name="first")
def first_workflow(param: str):
    return {"result": param}


@workflow(name="second")
def second_workflow(param: str):
    return {"result": param}
'''
        result = remove_function_from_source(source, "second_workflow")
        assert result is not None
        assert "second_workflow" not in result
        assert "first_workflow" in result

    def test_remove_middle_of_three_functions(self):
        """Remove the middle function from three."""
        source = '''from bifrost import workflow

@workflow(name="a")
def alpha():
    pass


@workflow(name="b")
def beta():
    pass


@workflow(name="c")
def gamma():
    pass
'''
        result = remove_function_from_source(source, "beta")
        assert result is not None
        assert "beta" not in result
        assert "alpha" in result
        assert "gamma" in result

    def test_async_function(self):
        """Handle async functions correctly."""
        source = '''from bifrost import workflow

@workflow(name="sync_one")
def sync_workflow():
    return {}


@workflow(name="async_one")
async def async_workflow():
    return {}
'''
        result = remove_function_from_source(source, "async_workflow")
        assert result is not None
        assert "async_workflow" not in result
        assert "sync_workflow" in result

    def test_multi_line_decorator(self):
        """Handle decorators with multiple keyword arguments spanning lines."""
        source = '''from bifrost import workflow

@workflow(
    name="detailed",
    description="A detailed workflow",
    category="Test",
)
def detailed_workflow(param: str):
    return {"result": param}


@workflow(name="simple")
def simple_workflow():
    return {}
'''
        result = remove_function_from_source(source, "detailed_workflow")
        assert result is not None
        assert "detailed_workflow" not in result
        assert "detailed" not in result  # decorator args removed too
        assert "simple_workflow" in result

    def test_multiple_decorators(self):
        """Handle functions with multiple decorators."""
        source = '''from bifrost import workflow

@some_other_decorator
@workflow(name="decorated")
def decorated_workflow():
    return {}


@workflow(name="plain")
def plain_workflow():
    return {}
'''
        result = remove_function_from_source(source, "decorated_workflow")
        assert result is not None
        assert "decorated_workflow" not in result
        assert "some_other_decorator" not in result
        assert "plain_workflow" in result

    def test_function_not_found_raises(self):
        """Raise ValueError if function doesn't exist."""
        source = '''def existing():
    pass
'''
        with pytest.raises(ValueError, match="not found"):
            remove_function_from_source(source, "nonexistent")

    def test_syntax_error_raises(self):
        """Raise ValueError for invalid Python source."""
        with pytest.raises(ValueError, match="Failed to parse"):
            remove_function_from_source("def broken(:", "broken")

    def test_preserves_imports_and_constants(self):
        """Imports and module-level code are preserved."""
        source = '''import os
from bifrost import workflow

CONSTANT = "hello"


@workflow(name="to_remove")
def remove_me():
    return {}


@workflow(name="to_keep")
def keep_me():
    return os.path.join(CONSTANT, "world")
'''
        result = remove_function_from_source(source, "remove_me")
        assert result is not None
        assert "import os" in result
        assert 'CONSTANT = "hello"' in result
        assert "keep_me" in result
        assert "remove_me" not in result

    def test_result_ends_with_newline(self):
        """Result always ends with a newline."""
        source = '''def a():
    pass

def b():
    pass'''
        result = remove_function_from_source(source, "a")
        assert result is not None
        assert result.endswith("\n")

    def test_no_excessive_blank_lines(self):
        """Collapse 3+ consecutive blank lines to 2."""
        source = '''def a():
    pass



def b():
    pass



def c():
    pass
'''
        result = remove_function_from_source(source, "b")
        assert result is not None
        # Should not have 3+ consecutive blank lines
        assert "\n\n\n\n" not in result
