"""
Unit tests for workflow and data provider decorators
Tests decorator metadata attachment and signature-based parameter extraction.

Note: With dynamic discovery, decorators no longer register with a global registry.
Instead, they attach metadata directly to decorated functions which is then
read during dynamic discovery. Parameters are now automatically extracted from
function signatures - no @param decorator needed.

## Decorator Parameters

Only identity parameters are accepted in decorators:
- name: Override function name (stable identifier)
- description: Override docstring
- category: Hint for organization (overridable in UI)
- tags: Hints for filtering (overridable in UI)
- is_tool: Mark as AI agent tool (@workflow only)

All other configuration (schedules, timeouts, endpoints, etc.) is managed via UI/API.
Unknown parameters are ignored with a warning for backwards compatibility.
"""


from src.sdk.decorators import data_provider, workflow


class TestWorkflowDecorator:
    """Test @workflow decorator"""

    def test_workflow_decorator_zero_arg(self):
        """Test zero-argument workflow decorator"""
        @workflow
        def test_func():
            """Test workflow function."""
            return "test result"

        # Verify function has metadata attached
        assert hasattr(test_func, '_executable_metadata')
        metadata = test_func._executable_metadata

        # Verify function still works normally
        result = test_func()
        assert result == "test result"

        # Verify metadata auto-derived
        assert metadata.name == "test_func"
        assert metadata.description == "Test workflow function."
        assert metadata.category == "General"
        assert metadata.tags == []
        assert metadata.type == "workflow"

    def test_workflow_decorator_basic(self):
        """Test basic workflow decorator"""
        @workflow(
            name="test_workflow",
            description="Test workflow"
        )
        def test_func():
            return "test result"

        # Verify function has metadata attached
        assert hasattr(test_func, '_executable_metadata')
        metadata = test_func._executable_metadata

        # Verify function still works normally
        result = test_func()
        assert result == "test result"

        # Verify metadata
        assert metadata.name == "test_workflow"
        assert metadata.description == "Test workflow"
        assert metadata.category == "General"
        assert metadata.tags == []
        assert metadata.type == "workflow"

    def test_workflow_decorator_full_options(self):
        """Test workflow decorator with all identity options"""
        @workflow(
            name="user_onboarding",
            description="Onboard new M365 user",
            category="user_management",
            tags=["m365", "user"]
        )
        def onboard_user(first_name: str, last_name: str):
            return f"Onboarded {first_name} {last_name}"

        metadata = onboard_user._executable_metadata
        assert metadata.category == "user_management"
        assert metadata.tags == ["m365", "user"]
        assert metadata.type == "workflow"

        # Verify function still callable
        result = onboard_user("John", "Doe")
        assert result == "Onboarded John Doe"

    def test_workflow_as_tool(self):
        """Test workflow marked as tool"""
        @workflow(
            name="get_user_tool",
            description="Get user info",
            is_tool=True
        )
        def get_user(email: str):
            return {"email": email}

        metadata = get_user._executable_metadata
        assert metadata.type == "tool"

    def test_workflow_unknown_params_logged_as_warning(self, caplog):
        """Test that unknown parameters are accepted but logged as warnings"""
        import logging
        with caplog.at_level(logging.WARNING):
            @workflow(
                name="legacy_workflow",
                description="Legacy workflow with old params",
                execution_mode="sync",  # Old param - should be ignored
                timeout_seconds=300,    # Old param - should be ignored
                endpoint_enabled=True,  # Old param - should be ignored
            )
            def legacy_func():
                return "legacy"

        # Verify warning was logged
        assert "Unknown @workflow parameters ignored" in caplog.text
        assert "endpoint_enabled" in caplog.text
        assert "execution_mode" in caplog.text
        assert "timeout_seconds" in caplog.text

        # Verify metadata uses defaults (not the passed values)
        metadata = legacy_func._executable_metadata
        assert metadata.type == "workflow"

    def test_workflow_function_metadata_preserved(self):
        """Test that function metadata is preserved"""
        @workflow(
            name="test_workflow",
            description="Test"
        )
        def test_func():
            """Original docstring"""
            pass

        assert hasattr(test_func, '_executable_metadata')
        assert test_func.__name__ == "test_func"
        assert test_func.__doc__ == "Original docstring"

    def test_workflow_name_auto_derived_from_function(self):
        """Test that name is derived from function name when not provided"""
        @workflow(description="A workflow")
        def my_cool_workflow():
            pass

        metadata = my_cool_workflow._executable_metadata
        assert metadata.name == "my_cool_workflow"

    def test_workflow_description_auto_derived_from_docstring(self):
        """Test that description is derived from docstring when not provided"""
        @workflow
        def my_workflow():
            """This is the auto-derived description."""
            pass

        metadata = my_workflow._executable_metadata
        assert metadata.description == "This is the auto-derived description."


class TestSignatureBasedParameters:
    """Test automatic parameter extraction from function signatures"""

    def test_parameters_extracted_from_signature(self):
        """Test that parameters are extracted from function signature"""
        @workflow
        def test_func(name: str, count: int = 5, active: bool = True):
            """Test workflow."""
            pass

        metadata = test_func._executable_metadata
        assert len(metadata.parameters) == 3

        # First param: name (required, no default)
        name_param = metadata.parameters[0]
        assert name_param.name == "name"
        assert name_param.type == "string"
        assert name_param.required is True
        assert name_param.default_value is None

        # Second param: count (optional, has default)
        count_param = metadata.parameters[1]
        assert count_param.name == "count"
        assert count_param.type == "int"
        assert count_param.required is False
        assert count_param.default_value == 5

        # Third param: active (optional, has default)
        active_param = metadata.parameters[2]
        assert active_param.name == "active"
        assert active_param.type == "bool"
        assert active_param.required is False
        assert active_param.default_value is True

    def test_parameters_labels_auto_generated(self):
        """Test that labels are auto-generated from parameter names"""
        @workflow
        def test_func(first_name: str, email_address: str):
            """Test."""
            pass

        metadata = test_func._executable_metadata
        assert metadata.parameters[0].label == "First Name"
        assert metadata.parameters[1].label == "Email Address"

    def test_optional_type_makes_not_required(self):
        """Test that Optional types are not required"""
        @workflow
        def test_func(name: str | None):
            """Test."""
            pass

        metadata = test_func._executable_metadata
        assert len(metadata.parameters) == 1
        assert metadata.parameters[0].required is False

    def test_list_type_mapping(self):
        """Test list type maps correctly"""
        @workflow
        def test_func(items: list):
            """Test."""
            pass

        metadata = test_func._executable_metadata
        assert metadata.parameters[0].type == "list"

    def test_dict_type_mapping(self):
        """Test dict type maps to json"""
        @workflow
        def test_func(config: dict):
            """Test."""
            pass

        metadata = test_func._executable_metadata
        assert metadata.parameters[0].type == "json"

    def test_float_type_mapping(self):
        """Test float type maps correctly"""
        @workflow
        def test_func(rate: float = 0.5):
            """Test."""
            pass

        metadata = test_func._executable_metadata
        assert metadata.parameters[0].type == "float"
        assert metadata.parameters[0].default_value == 0.5


class TestDataProviderDecorator:
    """Test @data_provider decorator"""

    def test_data_provider_decorator_basic(self):
        """Test basic data provider decorator"""
        @data_provider(
            name="get_licenses",
            description="Returns available licenses"
        )
        def get_licenses():
            return [{"label": "E5", "value": "SPE_E5"}]

        # Verify provider has metadata attached
        assert hasattr(get_licenses, '_executable_metadata')

        # Verify function still works
        result = get_licenses()
        assert result == [{"label": "E5", "value": "SPE_E5"}]

        # Verify metadata
        metadata = get_licenses._executable_metadata
        assert metadata.name == "get_licenses"
        assert metadata.description == "Returns available licenses"
        assert metadata.category == "General"
        assert metadata.type == "data_provider"

    def test_data_provider_decorator_full_options(self):
        """Test data provider with all identity options"""
        @data_provider(
            name="get_available_licenses",
            description="Returns available M365 licenses",
            category="m365",
            tags=["licensing", "m365"]
        )
        def get_available_licenses():
            return []

        metadata = get_available_licenses._executable_metadata
        assert metadata.category == "m365"
        assert metadata.tags == ["licensing", "m365"]
        assert metadata.type == "data_provider"

    def test_data_provider_unknown_params_logged_as_warning(self, caplog):
        """Test that unknown parameters are accepted but logged as warnings"""
        import logging
        with caplog.at_level(logging.WARNING):
            @data_provider(
                name="legacy_provider",
                description="Legacy provider with old params",
                cache_ttl_seconds=600,   # Old param - should be ignored
                timeout_seconds=120,     # Old param - should be ignored
            )
            def legacy_provider():
                return []

        # Verify warning was logged
        assert "Unknown @data_provider parameters ignored" in caplog.text
        assert "cache_ttl_seconds" in caplog.text
        assert "timeout_seconds" in caplog.text

        # Verify metadata uses defaults
        metadata = legacy_provider._executable_metadata
        assert metadata.type == "data_provider"

    def test_data_provider_function_metadata_preserved(self):
        """Test that function metadata is preserved"""
        @data_provider(
            name="test_provider",
            description="Test"
        )
        def test_func():
            """Original docstring"""
            return []

        assert hasattr(test_func, '_executable_metadata')
        assert test_func.__name__ == "test_func"
        assert test_func.__doc__ == "Original docstring"

    def test_data_provider_parameters_from_signature(self):
        """Test that data provider params are extracted from signature"""
        @data_provider(
            name="filtered_licenses",
            description="Returns filtered licenses"
        )
        def get_filtered_licenses(filter_text: str | None = None, limit: int = 10):
            return []

        metadata = get_filtered_licenses._executable_metadata
        assert len(metadata.parameters) == 2

        # First param: filter_text (optional - has None in union)
        filter_param = metadata.parameters[0]
        assert filter_param.name == "filter_text"
        assert filter_param.type == "string"
        assert filter_param.required is False

        # Second param: limit (optional - has default)
        limit_param = metadata.parameters[1]
        assert limit_param.name == "limit"
        assert limit_param.type == "int"
        assert limit_param.required is False
        assert limit_param.default_value == 10


class TestDecoratorIntegration:
    """Test decorators working together"""

    def test_workflow_with_params_and_data_provider(self):
        """Test complete workflow with signature-derived params"""
        # First register data provider
        @data_provider(
            name="get_available_licenses",
            description="Get licenses",
            category="m365"
        )
        def get_licenses():
            return [
                {"label": "E5", "value": "SPE_E5"},
                {"label": "E3", "value": "SPE_E3"}
            ]

        # Then register workflow - params derived from signature
        @workflow(
            name="user_onboarding",
            description="Onboard user",
            category="user_management",
            tags=["m365"]
        )
        def onboard_user(first_name: str, last_name: str, email: str, license: str = "SPE_E3"):
            return f"Created {email} with {license}"

        # Verify workflow has metadata
        workflow_meta = onboard_user._executable_metadata
        assert len(workflow_meta.parameters) == 4

        # Verify data provider has metadata
        provider_meta = get_licenses._executable_metadata
        assert provider_meta is not None

        # Verify both functions still work
        licenses = get_licenses()
        assert len(licenses) == 2

        result = onboard_user("John", "Doe", "john@example.com", "SPE_E5")
        assert "john@example.com" in result

    def test_multiple_workflows_with_metadata(self):
        """Test multiple workflows have independent metadata"""
        @workflow
        def func1(param1: str):
            """First workflow."""
            pass

        @workflow
        def func2(param2: int):
            """Second workflow."""
            pass

        # Both functions have metadata
        assert hasattr(func1, '_executable_metadata')
        assert hasattr(func2, '_executable_metadata')

        # Verify each has correct params
        w1 = func1._executable_metadata
        w2 = func2._executable_metadata

        assert w1.parameters[0].name == "param1"
        assert w2.parameters[0].name == "param2"
