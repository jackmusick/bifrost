"""
Bifrost Platform SDK

Provides Python API access to platform features from workflows.

All SDK methods are async and must be awaited.

Usage:
    from bifrost import organizations, workflows, files, forms, executions, roles
    from bifrost import config, integrations, ai, knowledge, tables

Example:
    # AI Completions
    response = await ai.complete("Summarize this text...")
    print(response.content)

    # Structured AI output with Pydantic
    from pydantic import BaseModel
    class Summary(BaseModel):
        title: str
        points: list[str]
    result = await ai.complete("Summarize...", response_format=Summary)
    print(result.title)  # Typed!

    # AI with RAG context
    response = await ai.complete(
        "What is our refund policy?",
        knowledge=["policies", "faq"]
    )

    # Streaming AI
    async for chunk in ai.stream("Write a story..."):
        print(chunk.content, end="")

    # Knowledge Store (RAG)
    await knowledge.store(
        "Our refund policy allows 30-day returns.",
        namespace="policies",
        key="refund-policy"
    )
    results = await knowledge.search("return policy", namespace="policies")
    for doc in results:
        print(doc.content, doc.score)

    # Create an organization
    org = await organizations.create("Acme Corp", domain="acme.com")

    # List workflows
    wf_list = await workflows.list()
    for wf in wf_list:
        print(wf.name, wf.description)

    # File operations (async)
    await files.write("data/temp.txt", "content", location="temp")
    data = await files.read("data/customers.csv", location="workspace")

    # List executions
    recent = await executions.list(limit=10)
    for execution in recent:
        print(f"{execution.workflow_name}: {execution.status}")

    # Create a role
    role = await roles.create("Manager", description="Can manage team data")

    # Manage configuration
    await config.set("api_url", "https://api.example.com")
    url = await config.get("api_url")
    cfg = await config.list()
    print(cfg.api_url)  # Dot notation access

    # Get integration with OAuth tokens
    integration = await integrations.get("HaloPSA")
    if integration and integration.oauth:
        client_id = integration.oauth.client_id
        refresh_token = integration.oauth.refresh_token
"""

# SDK Modules
from .ai import ai
from .config import config
from .executions import executions
from .files import files
from .forms import forms
from .integrations import integrations
from .knowledge import knowledge
from .organizations import organizations
from .roles import roles
from .tables import tables
from .users import users
from .workflows import workflows

# SDK Models (single source of truth)
from .models import (
    Organization,
    Role,
    UserPublic,
    FormPublic,
    WorkflowMetadata,
    WorkflowExecution,
    IntegrationData,
    OAuthCredentials,
    IntegrationMappingResponse,
    ConfigData,
    AIResponse,
    AIStreamChunk,
    KnowledgeDocument,
    NamespaceInfo,
    TableInfo,
    DocumentData,
    DocumentList,
)

# Import decorators - try platform module first, fall back to local SDK version
try:
    from src.sdk.decorators import workflow, data_provider, tool
    from src.sdk.context import ExecutionContext
except ImportError:
    # CLI/standalone mode - use local decorators
    from .decorators import workflow, data_provider, tool
    _ = WorkflowMetadata  # noqa: F401 - re-exported from .models above
    # Provide a minimal ExecutionContext for CLI mode
    ExecutionContext = None  # type: ignore

# Import context proxy for accessing ExecutionContext without parameter
from ._context import context

# SDK Errors - try platform module first, fall back to local definitions
try:
    from src.sdk.errors import UserError, WorkflowError, ValidationError, IntegrationError, ConfigurationError  # type: ignore[assignment]
except ImportError:
    # CLI/standalone mode - define minimal error classes
    class UserError(Exception):  # type: ignore[no-redef]
        """User-facing error with formatted message."""
        pass

    class WorkflowError(Exception):  # type: ignore[no-redef]
        """Workflow execution error."""
        pass

    class ValidationError(Exception):  # type: ignore[no-redef]
        """Validation error."""
        pass

    class IntegrationError(Exception):  # type: ignore[no-redef]
        """Integration error."""
        pass

    class ConfigurationError(Exception):  # type: ignore[no-redef]
        """Configuration error."""
        pass

# Enums - try platform module first, fall back to local definitions
try:
    from src.models.enums import ExecutionStatus, ConfigType, FormFieldType  # type: ignore[assignment]
except ImportError:
    from enum import Enum

    class ExecutionStatus(str, Enum):  # type: ignore[no-redef]
        """Workflow execution status."""
        PENDING = "pending"
        RUNNING = "running"
        COMPLETED = "completed"
        FAILED = "failed"
        CANCELLED = "cancelled"

    class ConfigType(str, Enum):  # type: ignore[no-redef]
        """Configuration value type."""
        STRING = "string"
        SECRET = "secret"
        JSON = "json"
        BOOL = "bool"
        INT = "int"

    class FormFieldType(str, Enum):  # type: ignore[no-redef]
        """Form field type."""
        TEXT = "text"
        NUMBER = "number"
        SELECT = "select"
        CHECKBOX = "checkbox"
        DATE = "date"

__all__ = [
    # SDK Modules
    'ai',
    'config',
    'executions',
    'files',
    'forms',
    'integrations',
    'knowledge',
    'organizations',
    'roles',
    'tables',
    'users',
    'workflows',
    # SDK Models
    'Organization',
    'Role',
    'UserPublic',
    'FormPublic',
    'WorkflowMetadata',
    'WorkflowExecution',
    'IntegrationData',
    'OAuthCredentials',
    'IntegrationMappingResponse',
    'ConfigData',
    'AIResponse',
    'AIStreamChunk',
    'KnowledgeDocument',
    'NamespaceInfo',
    'TableInfo',
    'DocumentData',
    'DocumentList',
    # Decorators
    'workflow',
    'data_provider',
    'tool',
    # Context
    'context',
    'ExecutionContext',
    # Enums
    'ExecutionStatus',
    'ConfigType',
    'FormFieldType',
    # Errors
    'UserError',
    'WorkflowError',
    'ValidationError',
    'IntegrationError',
    'ConfigurationError',
]

__version__ = '2.0.0'
