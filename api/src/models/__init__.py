"""
Bifrost Models

ORM models (database tables):
    from src.models import Organization, User, Form
    from src.models.orm import Organization, User, Form
    from src.models.orm.users import User  # Granular access

Pydantic contracts (API request/response):
    from src.models import OrganizationCreate, OrganizationPublic
    from src.models.contracts import OrganizationCreate, OrganizationPublic
    from src.models.contracts.users import UserCreate  # Granular access

Enums:
    from src.models import ExecutionStatus
    from src.models.enums import ExecutionStatus
"""

# ORM models (database tables)
from src.models.orm import (
    Base,
    Organization,
    User,
    Role,
    UserRole,
    Form,
    FormField,
    FormRole,
    Execution,
    ExecutionLog,
    Config,
    Workflow,
    DataProvider,
    OAuthProvider,
    OAuthToken,
    AuditLog,
    UserMFAMethod,
    MFARecoveryCode,
    TrustedDevice,
    UserOAuthAccount,
    SystemConfig,
    GlobalBranding,
    ExecutionMetricsDaily,
    PlatformMetricsSnapshot,
    WorkspaceFile,
    DeveloperContext,
    DeveloperApiKey,
)

# Pydantic schemas (API request/response) - from contracts/
# Re-export everything from contracts
from src.models.contracts import *  # noqa: F401, F403

# Enums
from src.models.enums import (
    ExecutionStatus,
    UserType,
    FormAccessLevel,
    FormFieldType,
    ConfigType,
    MFAMethodType,
    MFAMethodStatus,
)

# Import __all__ from contracts for completeness
from src.models.contracts import __all__ as _contracts_all

# Combine all exports
__all__ = [
    # Base
    "Base",
    # ORM models
    "Organization",
    "User",
    "Role",
    "UserRole",
    "Form",
    "FormField",
    "FormRole",
    "Execution",
    "ExecutionLog",
    "Config",
    "Workflow",
    "DataProvider",
    "OAuthProvider",
    "OAuthToken",
    "AuditLog",
    "UserMFAMethod",
    "MFARecoveryCode",
    "TrustedDevice",
    "UserOAuthAccount",
    "SystemConfig",
    "GlobalBranding",
    "ExecutionMetricsDaily",
    "PlatformMetricsSnapshot",
    "WorkspaceFile",
    "DeveloperContext",
    "DeveloperApiKey",
    # Enums
    "ExecutionStatus",
    "UserType",
    "FormAccessLevel",
    "FormFieldType",
    "ConfigType",
    "MFAMethodType",
    "MFAMethodStatus",
] + list(_contracts_all)
