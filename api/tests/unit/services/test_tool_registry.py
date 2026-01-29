"""
Unit tests for ToolRegistry and tool name normalization.

Tests cover:
- Tool name normalization with category prefixing
- ToolDefinition dataclass
- Tool registry functionality
"""

from src.services.tool_registry import _normalize_tool_name


class TestNormalizeToolName:
    """Test _normalize_tool_name function with various inputs."""

    def test_basic_name_without_category_gets_wf_prefix(self):
        """Names without category get 'wf_' prefix."""
        result = _normalize_tool_name("Add Comment")
        assert result == "wf_add_comment"

    def test_basic_name_with_none_category_gets_wf_prefix(self):
        """Names with None category get 'wf_' prefix."""
        result = _normalize_tool_name("Add Comment", category=None)
        assert result == "wf_add_comment"

    def test_basic_name_with_general_category_gets_wf_prefix(self):
        """Names with 'General' category get 'wf_' prefix."""
        result = _normalize_tool_name("Add Comment", category="General")
        assert result == "wf_add_comment"

    def test_general_category_case_insensitive(self):
        """'general' category (any case) gets 'wf_' prefix."""
        assert _normalize_tool_name("Test", category="general") == "wf_test"
        assert _normalize_tool_name("Test", category="GENERAL") == "wf_test"
        assert _normalize_tool_name("Test", category="GeNeRaL") == "wf_test"

    def test_explicit_category_becomes_prefix(self):
        """Names with explicit category get category prefix."""
        result = _normalize_tool_name("List Tickets", category="HaloPSA")
        assert result == "halopsa_list_tickets"

    def test_category_with_spaces(self):
        """Category with spaces is normalized (spaces become underscores)."""
        result = _normalize_tool_name("Create Asset", category="IT Glue")
        assert result == "it_glue_create_asset"

    def test_category_with_hyphens(self):
        """Category with hyphens is normalized (hyphens become underscores)."""
        result = _normalize_tool_name("Get User", category="Active-Directory")
        assert result == "active_directory_get_user"

    def test_special_characters_removed_from_name(self):
        """Special characters are removed from name."""
        result = _normalize_tool_name("Add Comment (Demo)")
        assert result == "wf_add_comment_demo"

    def test_special_characters_removed_from_category(self):
        """Special characters are removed from category (hyphens become underscores)."""
        result = _normalize_tool_name("Test", category="My-Category! #1")
        assert result == "my_category_1_test"

    def test_multiple_spaces_collapsed(self):
        """Multiple spaces collapse to single underscore."""
        result = _normalize_tool_name("Add   Multiple   Spaces")
        assert result == "wf_add_multiple_spaces"

    def test_leading_trailing_underscores_stripped(self):
        """Leading/trailing underscores are stripped from name."""
        result = _normalize_tool_name("_test_name_")
        assert result == "wf_test_name"

    def test_empty_string_name(self):
        """Empty string returns just prefix."""
        result = _normalize_tool_name("")
        assert result == "wf_"

    def test_empty_category_treated_as_none(self):
        """Empty string category is treated as None."""
        result = _normalize_tool_name("Test", category="")
        assert result == "wf_test"

    def test_collision_prevention_with_system_tool_names(self):
        """Workflow named like system tool gets prefixed to avoid collision."""
        # A workflow named "Execute Workflow" would normalize to 'execute_workflow'
        # which could collide with the system tool. With the prefix, it becomes:
        result = _normalize_tool_name("Execute Workflow")
        assert result == "wf_execute_workflow"
        # This is different from the system tool 'execute_workflow'

    def test_collision_prevention_with_search_knowledge(self):
        """Workflow named 'search knowledge' gets prefixed."""
        result = _normalize_tool_name("Search Knowledge")
        assert result == "wf_search_knowledge"

    def test_realistic_halopsa_workflow_names(self):
        """Test realistic HaloPSA workflow names."""
        assert _normalize_tool_name("List Agents", category="HaloPSA") == "halopsa_list_agents"
        assert _normalize_tool_name("Get Ticket", category="HaloPSA") == "halopsa_get_ticket"
        assert _normalize_tool_name("Add Note to Ticket", category="HaloPSA") == "halopsa_add_note_to_ticket"
        assert _normalize_tool_name("Update Asset", category="HaloPSA") == "halopsa_update_asset"

    def test_unicode_characters_removed(self):
        """Unicode characters are removed (only ASCII alphanumeric allowed)."""
        result = _normalize_tool_name("Créer Document", category="Système")
        assert result == "systme_crer_document"

    def test_numbers_preserved(self):
        """Numbers are preserved in names and categories."""
        result = _normalize_tool_name("API v2 Call", category="Service123")
        assert result == "service123_api_v2_call"


class TestToolDefinitionCategory:
    """Test that ToolDefinition includes category properly."""

    def test_tool_definition_has_category_field(self):
        """ToolDefinition should have a category field."""
        from uuid import uuid4
        from src.services.tool_registry import ToolDefinition

        td = ToolDefinition(
            id=uuid4(),
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
            workflow_name="Test Tool",
            category="TestCategory",
        )
        assert td.category == "TestCategory"

    def test_tool_definition_category_defaults_to_none(self):
        """ToolDefinition category defaults to None."""
        from uuid import uuid4
        from src.services.tool_registry import ToolDefinition

        td = ToolDefinition(
            id=uuid4(),
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
            workflow_name="Test Tool",
        )
        assert td.category is None
