"""
SDK Usage Scanner Service

Scans workspace Python files for Bifrost SDK calls (config.get, secrets.get, oauth.get_token)
and validates them against stored data to identify missing configurations.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.sdk.context import ExecutionContext
    from src.models.models import SDKUsageIssue

logger = logging.getLogger(__name__)

# Regex patterns to extract SDK calls
# Uses \b word boundary to avoid matching variables ending in the SDK name
# e.g., oauth_config.get() should NOT match config.get()

# Matches: config.get("key"), config.get('key'), await config.get("key"), etc.
CONFIG_GET_PATTERN = re.compile(
    r'''(?:await\s+)?\bconfig\.get\s*\(\s*["']([^"']+)["']''',
    re.MULTILINE
)

# Matches: secrets.get("key"), await secrets.get("key"), etc.
SECRETS_GET_PATTERN = re.compile(
    r'''(?:await\s+)?\bsecrets\.get\s*\(\s*["']([^"']+)["']''',
    re.MULTILINE
)

# Matches: oauth.get_token("provider"), await oauth.get_token("provider"), etc.
OAUTH_GET_TOKEN_PATTERN = re.compile(
    r'''(?:await\s+)?\boauth\.get_token\s*\(\s*["']([^"']+)["']''',
    re.MULTILINE
)


@dataclass
class SDKCall:
    """Represents a single SDK call found in code"""
    key: str
    line_number: int
    line_content: str


@dataclass
class FileSDKUsage:
    """SDK usage extracted from a single file"""
    file_path: str
    file_name: str
    config_calls: list[SDKCall] = field(default_factory=list)
    secret_calls: list[SDKCall] = field(default_factory=list)
    oauth_calls: list[SDKCall] = field(default_factory=list)

    @property
    def has_any_calls(self) -> bool:
        return bool(self.config_calls or self.secret_calls or self.oauth_calls)

    @property
    def has_config_calls(self) -> bool:
        return bool(self.config_calls)

    @property
    def has_secret_calls(self) -> bool:
        return bool(self.secret_calls)

    @property
    def has_oauth_calls(self) -> bool:
        return bool(self.oauth_calls)


class SDKUsageScanner:
    """
    Scans workspace files for SDK usage and validates against stored data.

    Two-phase approach:
    1. Extract SDK calls from files using regex (no backend queries)
    2. Only query backends for the types actually found
    """

    def __init__(self, workspace_path: str | Path):
        """
        Initialize scanner with workspace path.

        Args:
            workspace_path: Path to workspace directory to scan
        """
        self.workspace_path = Path(workspace_path)

    def extract_sdk_calls(self, content: str) -> FileSDKUsage:
        """
        Extract SDK calls from file content.

        Args:
            content: Python file content

        Returns:
            FileSDKUsage with extracted calls (file_path/file_name will be empty)
        """
        lines = content.split('\n')
        usage = FileSDKUsage(file_path="", file_name="")

        # Extract config.get() calls
        for match in CONFIG_GET_PATTERN.finditer(content):
            key = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            line_content = lines[line_num - 1].strip() if line_num <= len(lines) else ""
            usage.config_calls.append(SDKCall(key=key, line_number=line_num, line_content=line_content))

        # Extract secrets.get() calls
        for match in SECRETS_GET_PATTERN.finditer(content):
            key = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            line_content = lines[line_num - 1].strip() if line_num <= len(lines) else ""
            usage.secret_calls.append(SDKCall(key=key, line_number=line_num, line_content=line_content))

        # Extract oauth.get_token() calls
        for match in OAUTH_GET_TOKEN_PATTERN.finditer(content):
            provider = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            line_content = lines[line_num - 1].strip() if line_num <= len(lines) else ""
            usage.oauth_calls.append(SDKCall(key=provider, line_number=line_num, line_content=line_content))

        return usage

    def scan_file(self, file_path: Path) -> FileSDKUsage | None:
        """
        Scan a single Python file for SDK calls.

        Args:
            file_path: Absolute path to Python file

        Returns:
            FileSDKUsage or None if file can't be read
        """
        try:
            content = file_path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            return None

        usage = self.extract_sdk_calls(content)

        # Set file info
        try:
            relative_path = file_path.relative_to(self.workspace_path)
            usage.file_path = str(relative_path)
        except ValueError:
            usage.file_path = str(file_path)

        usage.file_name = file_path.name

        return usage

    def scan_workspace(self) -> list[FileSDKUsage]:
        """
        Scan all Python files in workspace for SDK calls.

        Returns:
            List of FileSDKUsage for files that have SDK calls
        """
        results = []

        if not self.workspace_path.exists():
            logger.warning(f"Workspace path does not exist: {self.workspace_path}")
            return results

        # Find all Python files
        for py_file in self.workspace_path.rglob("*.py"):
            # Skip __pycache__ and hidden directories
            if "__pycache__" in str(py_file) or any(part.startswith('.') for part in py_file.parts):
                continue

            usage = self.scan_file(py_file)
            if usage and usage.has_any_calls:
                results.append(usage)

        logger.info(f"Scanned workspace, found {len(results)} files with SDK calls")
        return results

    async def validate_workspace(
        self,
        context: 'ExecutionContext'
    ) -> 'list[SDKUsageIssue]':
        """
        Scan workspace and validate SDK calls against stored data.

        Args:
            context: Execution context for repository access

        Returns:
            List of SDKUsageIssue for missing configurations
        """
        from src.models.models import SDKUsageIssue, SDKUsageType

        # Phase 1: Scan all files
        file_usages = self.scan_workspace()

        if not file_usages:
            return []

        # Aggregate which types we need to query
        need_configs = any(f.has_config_calls for f in file_usages)
        need_secrets = any(f.has_secret_calls for f in file_usages)
        need_oauth = any(f.has_oauth_calls for f in file_usages)

        # Phase 2: Only query what we need
        stored_configs: set[str] = set()
        stored_secrets: set[str] = set()
        stored_oauth_providers: set[str] = set()

        if need_configs:
            stored_configs = await self._get_stored_config_keys(context)

        if need_secrets:
            stored_secrets = await self._get_stored_secret_keys(context)

        if need_oauth:
            stored_oauth_providers = await self._get_stored_oauth_providers(context)

        # Phase 3: Compare and generate issues
        issues: list[SDKUsageIssue] = []

        for file_usage in file_usages:
            # Check config calls
            for call in file_usage.config_calls:
                if call.key not in stored_configs:
                    issues.append(SDKUsageIssue(
                        file_path=file_usage.file_path,
                        file_name=file_usage.file_name,
                        type=SDKUsageType.CONFIG,
                        key=call.key,
                        line_number=call.line_number,
                    ))

            # Check secret calls
            for call in file_usage.secret_calls:
                if call.key not in stored_secrets:
                    issues.append(SDKUsageIssue(
                        file_path=file_usage.file_path,
                        file_name=file_usage.file_name,
                        type=SDKUsageType.SECRET,
                        key=call.key,
                        line_number=call.line_number,
                    ))

            # Check OAuth calls
            for call in file_usage.oauth_calls:
                if call.key not in stored_oauth_providers:
                    issues.append(SDKUsageIssue(
                        file_path=file_usage.file_path,
                        file_name=file_usage.file_name,
                        type=SDKUsageType.OAUTH,
                        key=call.key,
                        line_number=call.line_number,
                    ))

        logger.info(f"Validation complete: {len(issues)} issues found")
        return issues

    async def validate_file(
        self,
        file_path: str,
        context: 'ExecutionContext',
        content: str | None = None
    ) -> 'list[SDKUsageIssue]':
        """
        Validate a single file's SDK calls against stored data.

        Args:
            file_path: Relative path to file in workspace
            context: Execution context for repository access
            content: Optional file content (if not provided, reads from disk)

        Returns:
            List of SDKUsageIssue for missing configurations
        """
        from src.models.models import SDKUsageIssue, SDKUsageType

        full_path = self.workspace_path / file_path

        # Get file content
        if content is None:
            try:
                content = full_path.read_text(encoding='utf-8')
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(f"Failed to read {file_path}: {e}")
                return []

        # Extract SDK calls
        usage = self.extract_sdk_calls(content)
        usage.file_path = file_path
        usage.file_name = Path(file_path).name

        if not usage.has_any_calls:
            return []

        # Only query backends for types we found
        stored_configs: set[str] = set()
        stored_secrets: set[str] = set()
        stored_oauth_providers: set[str] = set()

        if usage.has_config_calls:
            stored_configs = await self._get_stored_config_keys(context)

        if usage.has_secret_calls:
            stored_secrets = await self._get_stored_secret_keys(context)

        if usage.has_oauth_calls:
            stored_oauth_providers = await self._get_stored_oauth_providers(context)

        # Generate issues
        issues: list[SDKUsageIssue] = []

        for call in usage.config_calls:
            if call.key not in stored_configs:
                issues.append(SDKUsageIssue(
                    file_path=usage.file_path,
                    file_name=usage.file_name,
                    type=SDKUsageType.CONFIG,
                    key=call.key,
                    line_number=call.line_number,
                ))

        for call in usage.secret_calls:
            if call.key not in stored_secrets:
                issues.append(SDKUsageIssue(
                    file_path=usage.file_path,
                    file_name=usage.file_name,
                    type=SDKUsageType.SECRET,
                    key=call.key,
                    line_number=call.line_number,
                ))

        for call in usage.oauth_calls:
            if call.key not in stored_oauth_providers:
                issues.append(SDKUsageIssue(
                    file_path=usage.file_path,
                    file_name=usage.file_name,
                    type=SDKUsageType.OAUTH,
                    key=call.key,
                    line_number=call.line_number,
                ))

        return issues

    async def _get_stored_config_keys(self, context: 'ExecutionContext') -> set[str]:
        """Get all stored config keys for the context's scope"""
        from uuid import UUID
        from sqlalchemy import select, or_

        try:
            from src.core.database import get_session_factory
            from src.models import Config

            session_factory = get_session_factory()
            org_id = getattr(context, 'org_id', None) or getattr(context, 'scope', None)
            org_uuid = None
            if org_id and org_id != "GLOBAL":
                try:
                    org_uuid = UUID(org_id)
                except ValueError:
                    pass

            async with session_factory() as db:
                # Get org-specific and GLOBAL configs
                if org_uuid:
                    query = select(Config.key).where(
                        or_(
                            Config.organization_id == org_uuid,
                            Config.organization_id.is_(None)
                        )
                    )
                else:
                    query = select(Config.key).where(Config.organization_id.is_(None))

                result = await db.execute(query)
                return {row[0] for row in result.all()}
        except Exception as e:
            logger.error(f"Failed to list configs: {e}")
            return set()

    async def _get_stored_secret_keys(self, context: 'ExecutionContext') -> set[str]:
        """Get all stored secret keys for the context's scope"""
        from uuid import UUID
        from sqlalchemy import select, or_

        try:
            from src.core.database import get_session_factory
            from src.models import Config
            from src.models.enums import ConfigType

            session_factory = get_session_factory()
            org_id = getattr(context, 'org_id', None) or getattr(context, 'scope', None)
            org_uuid = None
            if org_id and org_id != "GLOBAL":
                try:
                    org_uuid = UUID(org_id)
                except ValueError:
                    pass

            async with session_factory() as db:
                # Get org-specific and GLOBAL secrets (config entries with config_type=SECRET)
                if org_uuid:
                    query = select(Config.key).where(
                        Config.config_type == ConfigType.SECRET,
                        or_(
                            Config.organization_id == org_uuid,
                            Config.organization_id.is_(None)
                        )
                    )
                else:
                    query = select(Config.key).where(
                        Config.config_type == ConfigType.SECRET,
                        Config.organization_id.is_(None)
                    )

                result = await db.execute(query)
                return {row[0] for row in result.all()}
        except Exception as e:
            logger.error(f"Failed to list secrets: {e}")
            return set()

    async def _get_stored_oauth_providers(self, context: 'ExecutionContext') -> set[str]:
        """Get all stored OAuth providers with completed status"""
        from src.services.oauth_storage import OAuthStorageService

        try:
            service = OAuthStorageService()
            connections = await service.list_connections(context.scope, include_global=True)
            # Only include completed connections
            return {c.connection_name for c in connections if c.status == "completed"}
        except Exception as e:
            logger.error(f"Failed to list OAuth connections: {e}")
            return set()
