"""
Unit tests for SDKUsageScanner

Tests SDK usage extraction (regex patterns) and validation against stored data.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.sdk_usage_scanner import SDKUsageScanner, SDKCall, FileSDKUsage


class TestSDKCallExtraction:
    """Test regex extraction of SDK calls from Python code"""

    def test_extract_config_get_simple(self, tmp_path):
        """Should extract simple config.get calls"""
        code = '''
config.get("api_key")
config.get('database_url')
'''
        scanner = SDKUsageScanner(tmp_path)
        result = scanner.extract_sdk_calls(code)

        assert len(result.config_calls) == 2
        assert result.config_calls[0].key == "api_key"
        assert result.config_calls[0].line_number == 2
        assert result.config_calls[1].key == "database_url"
        assert result.config_calls[1].line_number == 3

    def test_extract_config_get_with_await(self, tmp_path):
        """Should extract async config.get calls"""
        code = '''
value = await config.get("async_key")
'''
        scanner = SDKUsageScanner(tmp_path)
        result = scanner.extract_sdk_calls(code)

        assert len(result.config_calls) == 1
        assert result.config_calls[0].key == "async_key"

    def test_extract_secrets_get(self, tmp_path):
        """Should extract secrets.get calls"""
        code = '''
password = secrets.get("db_password")
await secrets.get('api_secret')
'''
        scanner = SDKUsageScanner(tmp_path)
        result = scanner.extract_sdk_calls(code)

        assert len(result.secret_calls) == 2
        assert result.secret_calls[0].key == "db_password"
        assert result.secret_calls[1].key == "api_secret"

    def test_extract_oauth_get_token(self, tmp_path):
        """Should extract oauth.get_token calls"""
        code = '''
token = oauth.get_token("microsoft")
await oauth.get_token('google')
'''
        scanner = SDKUsageScanner(tmp_path)
        result = scanner.extract_sdk_calls(code)

        assert len(result.oauth_calls) == 2
        assert result.oauth_calls[0].key == "microsoft"
        assert result.oauth_calls[1].key == "google"

    def test_extract_mixed_calls(self, tmp_path):
        """Should extract all types of SDK calls"""
        code = '''
from bifrost import config, secrets, oauth

api_key = config.get("api_key")
password = secrets.get("password")
token = oauth.get_token("github")
'''
        scanner = SDKUsageScanner(tmp_path)
        result = scanner.extract_sdk_calls(code)

        assert len(result.config_calls) == 1
        assert len(result.secret_calls) == 1
        assert len(result.oauth_calls) == 1
        assert result.config_calls[0].key == "api_key"
        assert result.config_calls[0].line_number == 4
        assert result.secret_calls[0].key == "password"
        assert result.oauth_calls[0].key == "github"

    def test_extract_empty_file(self, tmp_path):
        """Should return empty results for file with no SDK calls"""
        code = '''
def hello():
    print("Hello World")
'''
        scanner = SDKUsageScanner(tmp_path)
        result = scanner.extract_sdk_calls(code)

        assert len(result.config_calls) == 0
        assert len(result.secret_calls) == 0
        assert len(result.oauth_calls) == 0
        assert not result.has_any_calls

    def test_extract_duplicate_keys(self, tmp_path):
        """Should extract duplicate keys with their line numbers"""
        code = '''
config.get("api_key")
config.get("api_key")
'''
        scanner = SDKUsageScanner(tmp_path)
        result = scanner.extract_sdk_calls(code)

        # Both occurrences should be found
        assert len(result.config_calls) == 2
        assert result.config_calls[0].line_number == 2
        assert result.config_calls[1].line_number == 3

    def test_no_match_variables_ending_in_sdk_name(self, tmp_path):
        """Should NOT match variables that end in SDK names (word boundary)"""
        code = '''
# These should NOT match - they're dict .get() calls, not Bifrost SDK calls
oauth_config.get("client_id")
my_config.get("api_key")
app_secrets.get("password")
custom_oauth.get_token("provider")

# These SHOULD match - actual Bifrost SDK calls
config.get("real_config")
secrets.get("real_secret")
oauth.get_token("real_provider")
'''
        scanner = SDKUsageScanner(tmp_path)
        result = scanner.extract_sdk_calls(code)

        # Should only match the real SDK calls
        assert len(result.config_calls) == 1
        assert result.config_calls[0].key == "real_config"

        assert len(result.secret_calls) == 1
        assert result.secret_calls[0].key == "real_secret"

        assert len(result.oauth_calls) == 1
        assert result.oauth_calls[0].key == "real_provider"


class TestScanFile:
    """Test single file scanning"""

    def test_scan_file_extracts_calls(self, tmp_path):
        """Should scan a file and extract SDK calls"""
        # Create test file
        test_file = tmp_path / "workflow.py"
        test_file.write_text('config.get("test_key")\nsecrets.get("password")')

        scanner = SDKUsageScanner(tmp_path)
        result = scanner.scan_file(test_file)

        assert result is not None
        assert result.file_name == "workflow.py"
        assert result.file_path == "workflow.py"
        assert len(result.config_calls) == 1
        assert len(result.secret_calls) == 1

    def test_scan_file_nonexistent(self, tmp_path):
        """Should return None for non-existent file"""
        scanner = SDKUsageScanner(tmp_path)
        result = scanner.scan_file(tmp_path / "nonexistent.py")

        assert result is None

    def test_scan_file_stores_relative_path(self, tmp_path):
        """Should store relative path in result"""
        # Create nested file
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        test_file = subdir / "workflow.py"
        test_file.write_text('config.get("key")')

        scanner = SDKUsageScanner(tmp_path)
        result = scanner.scan_file(test_file)

        assert result.file_path == "subdir/workflow.py"
        assert result.file_name == "workflow.py"


class TestScanWorkspace:
    """Test workspace scanning functionality"""

    def test_scan_workspace_finds_python_files(self, tmp_path):
        """Should scan all Python files in workspace"""
        # Create test files
        (tmp_path / "workflow1.py").write_text('config.get("key1")')
        (tmp_path / "workflow2.py").write_text('secrets.get("secret1")')
        (tmp_path / "readme.md").write_text("# README")

        scanner = SDKUsageScanner(tmp_path)
        results = scanner.scan_workspace()

        # Should only find Python files with SDK calls
        assert len(results) == 2

    def test_scan_workspace_skips_pycache(self, tmp_path):
        """Should skip __pycache__ directories"""
        # Create pycache file
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "cached.py").write_text('config.get("key")')

        # Create regular file
        (tmp_path / "workflow.py").write_text('config.get("key")')

        scanner = SDKUsageScanner(tmp_path)
        results = scanner.scan_workspace()

        # Should only find the regular file
        assert len(results) == 1
        assert results[0].file_name == "workflow.py"

    def test_scan_workspace_skips_hidden_dirs(self, tmp_path):
        """Should skip hidden directories"""
        # Create hidden dir
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret.py").write_text('config.get("key")')

        # Create regular file
        (tmp_path / "workflow.py").write_text('config.get("key")')

        scanner = SDKUsageScanner(tmp_path)
        results = scanner.scan_workspace()

        assert len(results) == 1
        assert results[0].file_name == "workflow.py"

    def test_scan_workspace_empty(self, tmp_path):
        """Should return empty list for empty workspace"""
        scanner = SDKUsageScanner(tmp_path)
        results = scanner.scan_workspace()

        assert results == []

    def test_scan_workspace_only_files_with_calls(self, tmp_path):
        """Should only return files that have SDK calls"""
        (tmp_path / "with_calls.py").write_text('config.get("key")')
        (tmp_path / "no_calls.py").write_text('print("hello")')

        scanner = SDKUsageScanner(tmp_path)
        results = scanner.scan_workspace()

        assert len(results) == 1
        assert results[0].file_name == "with_calls.py"


class TestValidateWorkspace:
    """Test workspace validation against stored data"""

    @pytest.fixture
    def mock_context(self):
        """Mock ExecutionContext"""
        context = MagicMock()
        context.scope = "test-org"
        return context

    @pytest.mark.asyncio
    async def test_validate_workspace_no_files(self, tmp_path, mock_context):
        """Should return empty when no files have SDK calls"""
        (tmp_path / "workflow.py").write_text('print("hello")')

        scanner = SDKUsageScanner(tmp_path)
        issues = await scanner.validate_workspace(mock_context)

        assert issues == []

    @pytest.mark.asyncio
    async def test_validate_workspace_missing_config(self, tmp_path, mock_context):
        """Should report issue for missing config"""
        (tmp_path / "workflow.py").write_text('config.get("missing_key")')

        with patch.object(
            SDKUsageScanner, '_get_stored_config_keys',
            new_callable=AsyncMock
        ) as mock_configs:
            mock_configs.return_value = set()  # No configs exist

            scanner = SDKUsageScanner(tmp_path)
            issues = await scanner.validate_workspace(mock_context)

            assert len(issues) == 1
            assert issues[0].type.value == "config"
            assert issues[0].key == "missing_key"
            assert issues[0].file_name == "workflow.py"

    @pytest.mark.asyncio
    async def test_validate_workspace_existing_config(self, tmp_path, mock_context):
        """Should not report issue for existing config"""
        (tmp_path / "workflow.py").write_text('config.get("existing_key")')

        with patch.object(
            SDKUsageScanner, '_get_stored_config_keys',
            new_callable=AsyncMock
        ) as mock_configs:
            mock_configs.return_value = {"existing_key"}

            scanner = SDKUsageScanner(tmp_path)
            issues = await scanner.validate_workspace(mock_context)

            assert len(issues) == 0

    @pytest.mark.asyncio
    async def test_validate_workspace_missing_secret(self, tmp_path, mock_context):
        """Should report issue for missing secret"""
        (tmp_path / "workflow.py").write_text('secrets.get("missing_secret")')

        with patch.object(
            SDKUsageScanner, '_get_stored_secret_keys',
            new_callable=AsyncMock
        ) as mock_secrets:
            mock_secrets.return_value = set()

            scanner = SDKUsageScanner(tmp_path)
            issues = await scanner.validate_workspace(mock_context)

            assert len(issues) == 1
            assert issues[0].type.value == "secret"
            assert issues[0].key == "missing_secret"

    @pytest.mark.asyncio
    async def test_validate_workspace_missing_oauth(self, tmp_path, mock_context):
        """Should report issue for missing OAuth connection"""
        (tmp_path / "workflow.py").write_text('oauth.get_token("missing_provider")')

        with patch.object(
            SDKUsageScanner, '_get_stored_oauth_providers',
            new_callable=AsyncMock
        ) as mock_oauth:
            mock_oauth.return_value = set()

            scanner = SDKUsageScanner(tmp_path)
            issues = await scanner.validate_workspace(mock_context)

            assert len(issues) == 1
            assert issues[0].type.value == "oauth"
            assert issues[0].key == "missing_provider"

    @pytest.mark.asyncio
    async def test_validate_workspace_multiple_issues(self, tmp_path, mock_context):
        """Should report all issues"""
        (tmp_path / "workflow.py").write_text('''
config.get("missing_config")
secrets.get("missing_secret")
oauth.get_token("missing_oauth")
''')

        with patch.object(
            SDKUsageScanner, '_get_stored_config_keys',
            new_callable=AsyncMock, return_value=set()
        ), patch.object(
            SDKUsageScanner, '_get_stored_secret_keys',
            new_callable=AsyncMock, return_value=set()
        ), patch.object(
            SDKUsageScanner, '_get_stored_oauth_providers',
            new_callable=AsyncMock, return_value=set()
        ):
            scanner = SDKUsageScanner(tmp_path)
            issues = await scanner.validate_workspace(mock_context)

            assert len(issues) == 3
            types = {i.type.value for i in issues}
            assert types == {"config", "secret", "oauth"}


class TestValidateFile:
    """Test single file validation"""

    @pytest.fixture
    def mock_context(self):
        """Mock ExecutionContext"""
        context = MagicMock()
        context.scope = "test-org"
        return context

    @pytest.mark.asyncio
    async def test_validate_file_with_content(self, tmp_path, mock_context):
        """Should validate provided content without reading from disk"""
        content = 'config.get("test_key")'

        with patch.object(
            SDKUsageScanner, '_get_stored_config_keys',
            new_callable=AsyncMock, return_value=set()
        ):
            scanner = SDKUsageScanner(tmp_path)
            issues = await scanner.validate_file("workflow.py", mock_context, content)

            assert len(issues) == 1
            assert issues[0].key == "test_key"

    @pytest.mark.asyncio
    async def test_validate_file_reads_from_disk(self, tmp_path, mock_context):
        """Should read content from disk when not provided"""
        (tmp_path / "workflow.py").write_text('secrets.get("db_pass")')

        with patch.object(
            SDKUsageScanner, '_get_stored_secret_keys',
            new_callable=AsyncMock, return_value=set()
        ):
            scanner = SDKUsageScanner(tmp_path)
            issues = await scanner.validate_file("workflow.py", mock_context)

            assert len(issues) == 1
            assert issues[0].key == "db_pass"

    @pytest.mark.asyncio
    async def test_validate_file_no_sdk_calls(self, tmp_path, mock_context):
        """Should return empty for file with no SDK calls"""
        content = 'print("hello")'

        scanner = SDKUsageScanner(tmp_path)
        issues = await scanner.validate_file("workflow.py", mock_context, content)

        assert issues == []


class TestEfficiency:
    """Test that scanner only queries necessary backends"""

    @pytest.fixture
    def mock_context(self):
        """Mock ExecutionContext"""
        context = MagicMock()
        context.scope = "test-org"
        return context

    @pytest.mark.asyncio
    async def test_only_queries_needed_backends(self, tmp_path, mock_context):
        """Should only query backends for SDK types found in code"""
        # Code only uses config.get
        (tmp_path / "workflow.py").write_text('config.get("test_key")')

        with patch.object(
            SDKUsageScanner, '_get_stored_config_keys',
            new_callable=AsyncMock, return_value=set()
        ) as mock_configs, patch.object(
            SDKUsageScanner, '_get_stored_secret_keys',
            new_callable=AsyncMock, return_value=set()
        ) as mock_secrets, patch.object(
            SDKUsageScanner, '_get_stored_oauth_providers',
            new_callable=AsyncMock, return_value=set()
        ) as mock_oauth:
            scanner = SDKUsageScanner(tmp_path)
            await scanner.validate_workspace(mock_context)

            # Should query configs (used in code)
            mock_configs.assert_called_once()

            # Should NOT query secrets or oauth (not used in code)
            mock_secrets.assert_not_called()
            mock_oauth.assert_not_called()


class TestFileSDKUsageProperties:
    """Test FileSDKUsage helper properties"""

    def test_has_any_calls_true(self):
        """Should return True when any calls exist"""
        usage = FileSDKUsage(
            file_path="test.py",
            file_name="test.py",
            config_calls=[SDKCall(key="k", line_number=1, line_content="")]
        )
        assert usage.has_any_calls is True

    def test_has_any_calls_false(self):
        """Should return False when no calls exist"""
        usage = FileSDKUsage(file_path="test.py", file_name="test.py")
        assert usage.has_any_calls is False

    def test_has_config_calls(self):
        """Should correctly report config call presence"""
        usage = FileSDKUsage(
            file_path="test.py",
            file_name="test.py",
            config_calls=[SDKCall(key="k", line_number=1, line_content="")]
        )
        assert usage.has_config_calls is True
        assert usage.has_secret_calls is False
        assert usage.has_oauth_calls is False
