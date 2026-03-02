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
from datetime import datetime, timezone
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
    is_provider: bool = False

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
class ROIContext:
    """
    ROI tracking for workflow executions.

    Initialized from workflow defaults, can be modified during execution.
    Final values are captured when execution completes.
    """
    time_saved: int = 0   # Minutes saved, initialized from workflow default
    value: float = 0.0    # Value generated, initialized from workflow default


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
    workflow_name: str = field(default="")  # Name of the executing workflow

    # ==================== PLATFORM ====================
    # Public URL for constructing external links (e.g., workflow URLs, execution URLs)
    public_url: str = field(default="http://localhost:8000")

    # ==================== DATABASE SESSION ====================
    # Database session for SDK operations (injected during execution)
    _db: "AsyncSession | None" = field(default=None, repr=False)

    # ==================== EXECUTION PARAMETERS ====================
    # All parameters passed to the workflow/script execution
    # Access via context.parameters.get('param_name') or context.parameters['param_name']
    parameters: dict[str, Any] = field(default_factory=dict)

    # ==================== LAUNCH WORKFLOW DATA ====================
    # Results from the launch workflow (pre-execution context population)
    # Access via context.startup (None if no launch workflow)
    startup: dict[str, Any] | None = field(default=None)

    # ==================== ROI ====================
    # ROI tracking - initialized from workflow defaults, modifiable during execution
    roi: ROIContext = field(default_factory=ROIContext)

    # ==================== WORKFLOW STATE (private) ====================
    _config: dict[str, Any] = field(default_factory=dict)
    _config_resolver: ConfigResolver = field(default_factory=ConfigResolver)
    _integration_cache: dict = field(default_factory=dict)
    _integration_calls: list = field(default_factory=list)
    _dynamic_secrets: set[str] = field(default_factory=set, repr=False)
    _scope_override: str | None = field(default=None, repr=False)

    # ==================== COMPUTED PROPERTIES ====================

    @property
    def org_id(self) -> str | None:
        """Organization ID (None for GLOBAL scope)"""
        if self._scope_override is not None:
            return self._scope_override
        return self.organization.id if self.organization else None

    @property
    def org_name(self) -> str | None:
        """Organization name (None for GLOBAL scope)"""
        return self.organization.name if self.organization else None

    @property
    def is_global_scope(self) -> bool:
        """True if executing in GLOBAL scope (no organization)"""
        return self.scope == "GLOBAL"

    def set_scope(self, org_id: str | None) -> None:
        """Override the effective scope for all subsequent SDK calls.

        Only provider organizations can override to a different org.
        Pass None to reset to the original scope.
        """
        if org_id is None:
            self._scope_override = None
            return
        original_org_id = self.organization.id if self.organization else None
        if org_id == original_org_id:
            self._scope_override = None
            return
        if not self.organization or not self.organization.is_provider:
            raise PermissionError(
                f"Scope override to '{org_id}' denied. "
                "Only provider organizations can access other org scopes."
            )
        self._scope_override = org_id

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
            "timestamp": datetime.now(timezone.utc).isoformat(),
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

    def _collect_secret_values(self) -> set[str]:
        """
        Collect all decrypted secret values from config for scrubbing.

        Returns a set of plaintext secret values that should be redacted
        from execution output. Skips secrets shorter than 4 characters
        to avoid false positive redactions.
        """
        from src.core.secret_string import _MIN_SECRET_LENGTH

        secrets: set[str] = set()
        for entry in self._config.values():
            if isinstance(entry, dict) and entry.get("type") == "secret":
                try:
                    from src.core.security import decrypt_secret
                    decrypted = decrypt_secret(entry["value"])
                    if len(decrypted) >= _MIN_SECRET_LENGTH:
                        secrets.add(decrypted)
                except Exception:
                    pass  # Skip entries that fail to decrypt
        return secrets | self._dynamic_secrets

    def _register_dynamic_secret(self, value: str | None) -> None:
        """Register a dynamically obtained secret value for output scrubbing."""
        from src.core.secret_string import _MIN_SECRET_LENGTH
        if value and len(value) >= _MIN_SECRET_LENGTH:
            self._dynamic_secrets.add(value)


# Backward compatibility alias
OrganizationContext = ExecutionContext
