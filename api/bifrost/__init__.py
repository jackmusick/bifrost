"""
Bifrost Platform SDK

Provides Python API access to platform features from workflows.

All SDK methods are async and must be awaited.

Usage:
    from bifrost import organizations, workflows, files, forms, executions, roles
    from bifrost import config, oauth

Example:
    # Create an organization
    org = await organizations.create("Acme Corp", domain="acme.com")

    # List workflows
    wf_list = await workflows.list()

    # Local filesystem operations
    files.write("data/temp.txt", "content", location="temp")
    data = files.read("data/customers.csv", location="workspace")

    # List executions
    recent = await executions.list(limit=10)

    # Create a role
    role = await roles.create("Manager", permissions=["users.read", "users.write"])

    # Manage configuration
    await config.set("api_url", "https://api.example.com")
    url = await config.get("api_url")

    # Get OAuth tokens (for secrets, use config with is_secret=True)
    conn = await oauth.get("microsoft")
"""

from dataclasses import dataclass

from .config import config
from .executions import executions
from .files import files
from .forms import forms
from .oauth import oauth
from .organizations import organizations
from .roles import roles
from .workflows import workflows

# Import decorators and context from shared module
from src.sdk.decorators import workflow, data_provider
from src.sdk.context import ExecutionContext, Organization

# Import context proxy for accessing ExecutionContext without parameter
from ._context import context
from src.sdk.errors import UserError, WorkflowError, ValidationError, IntegrationError, ConfigurationError
from src.models.enums import ExecutionStatus, ConfigType, FormFieldType
from src.models import (
    OAuthCredentials,
    IntegrationType,
    Role,
    Form,
)

# For backwards compatibility with type stubs
@dataclass
class Caller:
    """User who triggered the workflow execution."""
    user_id: str
    email: str
    name: str

__all__ = [
    'organizations',
    'workflows',
    'files',
    'forms',
    'executions',
    'roles',
    'config',
    'oauth',
    'workflow',
    'data_provider',
    'context',
    'ExecutionContext',
    'Organization',
    'Caller',
    'ExecutionStatus',
    'OAuthCredentials',
    'ConfigType',
    'FormFieldType',
    'IntegrationType',
    'Role',
    'Form',
    'UserError',
    'WorkflowError',
    'ValidationError',
    'IntegrationError',
    'ConfigurationError',
]

__version__ = '2.0.0'
