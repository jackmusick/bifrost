"""
Unit tests for SDK Reference Scanner Service.

Tests the regex extraction and validation logic for detecting
missing config and integration references in Python files.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.sdk_reference_scanner import (
    SDKReferenceScanner,
    SDKIssue,
    CONFIG_PATTERN,
    INTEGRATIONS_PATTERN,
)


class TestPatternMatching:
    """Test regex pattern matching."""

    def test_config_pattern_basic(self):
        """Test basic config.get pattern."""
        code = '''config.get("api_key")'''
        matches = CONFIG_PATTERN.findall(code)
        assert matches == ["api_key"]

    def test_config_pattern_with_await(self):
        """Test config.get with await."""
        code = '''await config.get("api_key")'''
        matches = CONFIG_PATTERN.findall(code)
        assert matches == ["api_key"]

    def test_config_pattern_single_quotes(self):
        """Test config.get with single quotes."""
        code = '''config.get('api_key')'''
        matches = CONFIG_PATTERN.findall(code)
        assert matches == ["api_key"]

    def test_config_pattern_multiple(self):
        """Test multiple config.get calls."""
        code = '''
        url = await config.get("api_url")
        key = await config.get("api_key")
        timeout = config.get('timeout')
        '''
        matches = CONFIG_PATTERN.findall(code)
        assert set(matches) == {"api_url", "api_key", "timeout"}

    def test_config_pattern_ignores_default_value(self):
        """Test that config.get with default value is ignored."""
        code = '''config.get("optional_key", "default_value")'''
        matches = CONFIG_PATTERN.findall(code)
        assert matches == []

    def test_config_pattern_ignores_default_with_await(self):
        """Test that await config.get with default value is ignored."""
        code = '''await config.get("optional_key", "default")'''
        matches = CONFIG_PATTERN.findall(code)
        assert matches == []

    def test_config_pattern_ignores_default_single_quotes(self):
        """Test that config.get with default value using single quotes is ignored."""
        code = '''config.get('optional_key', 'default')'''
        matches = CONFIG_PATTERN.findall(code)
        assert matches == []

    def test_config_pattern_mixed_with_and_without_defaults(self):
        """Test mix of config.get with and without defaults."""
        code = '''
        required = config.get("required_key")
        optional = config.get("optional_key", "default")
        also_required = await config.get("another_required")
        also_optional = await config.get("another_optional", None)
        '''
        matches = CONFIG_PATTERN.findall(code)
        assert set(matches) == {"required_key", "another_required"}

    def test_integrations_pattern_basic(self):
        """Test basic integrations.get pattern."""
        code = '''integrations.get("HaloPSA")'''
        matches = INTEGRATIONS_PATTERN.findall(code)
        assert matches == ["HaloPSA"]

    def test_integrations_pattern_with_await(self):
        """Test integrations.get with await."""
        code = '''await integrations.get("HaloPSA")'''
        matches = INTEGRATIONS_PATTERN.findall(code)
        assert matches == ["HaloPSA"]

    def test_integrations_pattern_single_quotes(self):
        """Test integrations.get with single quotes."""
        code = '''integrations.get('Microsoft Partner')'''
        matches = INTEGRATIONS_PATTERN.findall(code)
        assert matches == ["Microsoft Partner"]

    def test_integrations_pattern_multiple(self):
        """Test multiple integrations.get calls."""
        code = '''
        halo = await integrations.get("HaloPSA")
        msft = await integrations.get("Microsoft Partner")
        '''
        matches = INTEGRATIONS_PATTERN.findall(code)
        assert set(matches) == {"HaloPSA", "Microsoft Partner"}

    def test_pattern_ignores_comments(self):
        """Test that patterns work even in commented code (we scan all)."""
        code = '''
        # config.get("commented_out")
        real = config.get("real_key")
        '''
        matches = CONFIG_PATTERN.findall(code)
        # Both match - we don't parse comments
        assert "real_key" in matches
        assert "commented_out" in matches

    def test_pattern_ignores_other_methods(self):
        """Test that patterns don't match other get methods."""
        code = '''
        other.get("something")
        dictionary.get("key")
        configuration.get("value")
        '''
        config_matches = CONFIG_PATTERN.findall(code)
        integration_matches = INTEGRATIONS_PATTERN.findall(code)
        assert config_matches == []
        assert integration_matches == []


class TestExtractReferences:
    """Test the extract_references method."""

    @pytest.fixture
    def scanner(self):
        """Create scanner with mock db."""
        mock_db = MagicMock()
        return SDKReferenceScanner(mock_db)

    def test_extract_empty_file(self, scanner):
        """Test extracting from empty file."""
        config_refs, integration_refs = scanner.extract_references("")
        assert config_refs == set()
        assert integration_refs == set()

    def test_extract_no_sdk_calls(self, scanner):
        """Test extracting from file with no SDK calls."""
        code = '''
        def hello():
            return "world"
        '''
        config_refs, integration_refs = scanner.extract_references(code)
        assert config_refs == set()
        assert integration_refs == set()

    def test_extract_mixed_calls(self, scanner):
        """Test extracting both config and integration calls."""
        code = '''
        from bifrost import config, integrations

        async def my_workflow():
            api_key = await config.get("api_key")
            url = await config.get("base_url")
            halo = await integrations.get("HaloPSA")
            return api_key, url, halo
        '''
        config_refs, integration_refs = scanner.extract_references(code)
        assert config_refs == {"api_key", "base_url"}
        assert integration_refs == {"HaloPSA"}

    def test_extract_deduplicates(self, scanner):
        """Test that duplicate references are deduplicated."""
        code = '''
        key1 = await config.get("api_key")
        key2 = await config.get("api_key")  # Same key again
        '''
        config_refs, integration_refs = scanner.extract_references(code)
        assert config_refs == {"api_key"}


class TestFindLineNumber:
    """Test the _find_line_number method."""

    @pytest.fixture
    def scanner(self):
        """Create scanner with mock db."""
        mock_db = MagicMock()
        return SDKReferenceScanner(mock_db)

    def test_find_line_number_basic(self, scanner):
        """Test finding line number."""
        lines = [
            "from bifrost import config",
            "",
            "key = config.get('api_key')",
        ]
        line_num = scanner._find_line_number(lines, "config.get", "api_key")
        assert line_num == 3

    def test_find_line_number_with_await(self, scanner):
        """Test finding line number with await."""
        lines = [
            "from bifrost import config",
            "key = await config.get('api_key')",
        ]
        line_num = scanner._find_line_number(lines, "config.get", "api_key")
        assert line_num == 2

    def test_find_line_number_not_found(self, scanner):
        """Test default to line 1 when not found."""
        lines = ["some code", "more code"]
        line_num = scanner._find_line_number(lines, "config.get", "missing")
        assert line_num == 1


class TestScanFile:
    """Test the scan_file method."""

    @pytest.fixture
    def scanner(self):
        """Create scanner with mock db."""
        mock_db = AsyncMock()
        return SDKReferenceScanner(mock_db)

    @pytest.mark.asyncio
    async def test_scan_file_no_issues(self, scanner):
        """Test scanning file with all valid references."""
        code = '''
        key = await config.get("api_key")
        halo = await integrations.get("HaloPSA")
        '''

        # Mock database to return the keys as existing
        scanner.get_all_config_keys = AsyncMock(return_value={"api_key"})
        scanner.get_all_mapped_integrations = AsyncMock(return_value={"HaloPSA"})

        issues = await scanner.scan_file("test.py", code)
        assert issues == []

    @pytest.mark.asyncio
    async def test_scan_file_missing_config(self, scanner):
        """Test scanning file with missing config."""
        code = '''key = await config.get("missing_key")'''

        scanner.get_all_config_keys = AsyncMock(return_value={"other_key"})
        scanner.get_all_mapped_integrations = AsyncMock(return_value=set())

        issues = await scanner.scan_file("test.py", code)

        assert len(issues) == 1
        assert issues[0].file_path == "test.py"
        assert issues[0].issue_type == "config"
        assert issues[0].key == "missing_key"

    @pytest.mark.asyncio
    async def test_scan_file_missing_integration(self, scanner):
        """Test scanning file with missing integration."""
        code = '''halo = await integrations.get("UnknownIntegration")'''

        scanner.get_all_config_keys = AsyncMock(return_value=set())
        scanner.get_all_mapped_integrations = AsyncMock(return_value={"HaloPSA"})

        issues = await scanner.scan_file("test.py", code)

        assert len(issues) == 1
        assert issues[0].file_path == "test.py"
        assert issues[0].issue_type == "integration"
        assert issues[0].key == "UnknownIntegration"

    @pytest.mark.asyncio
    async def test_scan_file_multiple_issues(self, scanner):
        """Test scanning file with multiple issues."""
        code = '''
        key1 = await config.get("missing_config")
        key2 = await config.get("another_missing")
        halo = await integrations.get("MissingIntegration")
        '''

        scanner.get_all_config_keys = AsyncMock(return_value=set())
        scanner.get_all_mapped_integrations = AsyncMock(return_value=set())

        issues = await scanner.scan_file("test.py", code)

        assert len(issues) == 3
        issue_keys = {i.key for i in issues}
        assert issue_keys == {"missing_config", "another_missing", "MissingIntegration"}

    @pytest.mark.asyncio
    async def test_scan_file_empty(self, scanner):
        """Test scanning empty file."""
        issues = await scanner.scan_file("test.py", "")
        assert issues == []

    @pytest.mark.asyncio
    async def test_scan_file_no_sdk_calls(self, scanner):
        """Test scanning file with no SDK calls."""
        code = '''
        def hello():
            return "world"
        '''
        issues = await scanner.scan_file("test.py", code)
        assert issues == []


class TestSDKIssueDataclass:
    """Test the SDKIssue dataclass."""

    def test_sdk_issue_creation(self):
        """Test creating SDKIssue."""
        issue = SDKIssue(
            file_path="workflows/my_workflow.py",
            line_number=42,
            issue_type="config",
            key="api_key",
        )
        assert issue.file_path == "workflows/my_workflow.py"
        assert issue.line_number == 42
        assert issue.issue_type == "config"
        assert issue.key == "api_key"

    def test_sdk_issue_integration_type(self):
        """Test SDKIssue with integration type."""
        issue = SDKIssue(
            file_path="test.py",
            line_number=10,
            issue_type="integration",
            key="HaloPSA",
        )
        assert issue.issue_type == "integration"
        assert issue.key == "HaloPSA"
