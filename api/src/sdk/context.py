"""
Organization Context
Context object passed to all workflows with org data, config, secrets, and integrations

Execution Context - Unified context for all requests, workflows, and scripts

This replaces both ExecutionContext and ExecutionContext with a single,
unified context that works everywhere:
- HTTP endpoint handlers
- Workflows and data providers
- Scripts
- Bifrost SDK
- Repository queries
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from src.core.config_resolver import ConfigResolver

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class Organization:
    """Organization entity."""
    id: str
    name: str
    is_active: bool = True

    @property
    def org_id(self) -> str:
        """Backwards compatibility: alias for id"""
        return self.id


@dataclass
class Caller:
    """User who triggered the execution."""
    user_id: str
    email: str
    name: str


@dataclass
class ExecutionContext:
    """
    Unified execution context for all code execution.

    Provides:
    - User identity (user_id, email, name)
    - Scope (GLOBAL or organization ID)
    - Authorization (is_platform_admin, is_function_key)
    - Configuration and secrets
    - Workflow state tracking (logs, variables, checkpoints)

    Used everywhere:
    - HTTP handlers receive this from middleware
    - Workflows receive this as first parameter
    - Scripts have this available as `context`
    - Bifrost SDK accesses this via ContextVar
    - Repositories use this for scoped queries
    """

    # ==================== IDENTITY ====================
    user_id: str
    email: str
    name: str

    # ==================== SCOPE ====================
    scope: str  # "GLOBAL" or organization ID
    organization: Organization | None  # None for GLOBAL scope

    # ==================== AUTHORIZATION ====================
    is_platform_admin: bool
    is_function_key: bool

    # ==================== EXECUTION ====================
    execution_id: str

    # ==================== DATABASE SESSION ====================
    # Database session for SDK operations (injected during execution)
    _db: "AsyncSession | None" = field(default=None, repr=False)

    # ==================== EXECUTION PARAMETERS ====================
    # Extra parameters passed to the workflow/script that don't match function signature
    # Access via context.parameters.get('param_name')
    parameters: dict[str, Any] = field(default_factory=dict)

    # ==================== WORKFLOW STATE (private) ====================
    _config: dict[str, Any] = field(default_factory=dict)
    _config_resolver: ConfigResolver = field(default_factory=ConfigResolver)
    _integration_cache: dict = field(default_factory=dict)
    _integration_calls: list = field(default_factory=list)

    # ==================== COMPUTED PROPERTIES ====================

    @property
    def org_id(self) -> str | None:
        """Organization ID (None for GLOBAL scope)"""
        return self.organization.id if self.organization else None

    @property
    def org_name(self) -> str | None:
        """Organization name (None for GLOBAL scope)"""
        return self.organization.name if self.organization else None

    @property
    def is_global_scope(self) -> bool:
        """True if executing in GLOBAL scope (no organization)"""
        return self.scope == "GLOBAL"

    @property
    def db(self) -> "AsyncSession":
        """
        Database session for SDK operations.

        Raises:
            RuntimeError: If no database session is available
        """
        if self._db is None:
            raise RuntimeError(
                "No database session available. "
                "SDK operations require a database context."
            )
        return self._db

    @property
    def executed_by(self) -> str:
        """Backwards compatibility: alias for user_id"""
        return self.user_id

    @property
    def executed_by_email(self) -> str:
        """Backwards compatibility: alias for email"""
        return self.email

    @property
    def executed_by_name(self) -> str:
        """Backwards compatibility: alias for name"""
        return self.name


    # ==================== STATE TRACKING ====================

    def _track_integration_call(
        self,
        integration: str,
        method: str,
        endpoint: str,
        status_code: int,
        duration_ms: int,
        error: str | None = None
    ) -> None:
        """
        Track external integration call.

        Called automatically by integration clients.
        """
        call_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "integration": integration,
            "method": method,
            "endpoint": endpoint,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "error": error,
            "success": status_code < 400 and not error
        }
        self._integration_calls.append(call_record)

    async def get_config(self, key: str, default: Any = ...) -> Any:
        """
        Get a configuration value.

        Automatically handles:
        - Org-scoped config lookup (org config overrides global)
        - Secret decryption for secret-type configs
        - Type parsing (int, bool, json)

        Args:
            key: Configuration key
            default: Default value if key not found. If not provided, raises KeyError.

        Returns:
            Configuration value (with secrets decrypted if applicable)

        Raises:
            KeyError: If key not found and no default provided
        """
        org_id = self.scope if self.scope != "GLOBAL" else "GLOBAL"
        return await self._config_resolver.get_config(org_id, key, self._config, default)

    async def finalize_execution(self) -> dict[str, Any]:
        """
        Get final execution state for persistence.

        Called automatically at end of execution.

        Returns:
            Dict with integration_calls
        """
        return {
            "integration_calls": self._integration_calls,
        }
