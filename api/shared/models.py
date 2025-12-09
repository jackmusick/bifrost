"""
Pydantic models for Bifrost Integrations
Request/response validation and serialization
"""

import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

# ==================== PUBLIC API ====================
# All models exported for OpenAPI spec generation

__all__ = [
    # Enums
    'ConfigType',
    'ExecutionStatus',
    'RetryPolicy',
    'FormFieldType',
    'FormAccessLevel',
    'IntegrationType',
    'UserType',

    # Organizations
    'Organization',
    'CreateOrganizationRequest',
    'UpdateOrganizationRequest',

    # Config
    'Config',
    'SetConfigRequest',

    # Integration Config
    'IntegrationConfig',
    'SetIntegrationConfigRequest',

    # Users & Roles
    'User',
    'CreateUserRequest',
    'UpdateUserRequest',
    'Role',
    'CreateRoleRequest',
    'UpdateRoleRequest',
    'UserRole',
    'FormRole',
    'RoleUsersResponse',
    'RoleFormsResponse',
    'AssignUsersToRoleRequest',
    'AssignFormsToRoleRequest',

    # Auth & MFA
    'OAuthProviderInfo',
    'AuthStatusResponse',
    'MFARequiredResponse',
    'MFASetupRequiredResponse',
    'MFAVerifyRequest',
    'LoginResponse',
    'TokenRefresh',
    'UserResponse',
    'MFASetupTokenRequest',
    'MFASetupResponse',
    'MFAEnrollVerifyRequest',
    'MFAEnrollVerifyResponse',
    'OAuthLoginRequest',

    # Permissions
    'UserPermission',
    'PermissionsData',
    'GrantPermissionsRequest',
    'UserRolesResponse',
    'UserFormsResponse',

    # Forms
    'FormFieldValidation',
    'FormField',
    'FormSchema',
    'Form',
    'CreateFormRequest',
    'UpdateFormRequest',
    'FormExecuteRequest',
    'FormStartupResponse',

    # Workflow Execution
    'ExecutionLog',
    'WorkflowExecution',
    'WorkflowExecutionRequest',
    'WorkflowExecutionResponse',
    'ExecutionsListResponse',
    'StuckExecutionsResponse',
    'CleanupTriggeredResponse',

    # System Logs
    'SystemLog',
    'SystemLogsListResponse',

    # Metadata
    'WorkflowParameter',
    'WorkflowMetadata',
    'DataProviderMetadata',
    'MetadataResponse',
    'FormDiscoveryMetadata',

    # Workflow Validation
    'ValidationIssue',
    'WorkflowValidationRequest',
    'WorkflowValidationResponse',

    # Data Providers
    'DataProviderInputMode',
    'DataProviderInputConfig',
    'DataProviderRequest',
    'DataProviderOption',
    'DataProviderResponse',

    # Secrets
    'SecretListResponse',
    'SecretCreateRequest',
    'SecretUpdateRequest',
    'SecretResponse',

    # Health
    'HealthCheck',
    'GeneralHealthResponse',
    'KeyVaultHealthResponse',

    # Dashboard
    'ExecutionStats',
    'RecentFailure',
    'DashboardMetricsResponse',
    'PlatformMetricsSnapshot',
    'DailyMetricsEntry',
    'DailyMetricsResponse',
    'OrganizationMetricsSummary',
    'OrganizationMetricsResponse',
    'ResourceMetricsEntry',
    'ResourceMetricsResponse',

    # OAuth Connection models
    'OAuthFlowType',
    'OAuthStatus',
    'CreateOAuthConnectionRequest',
    'UpdateOAuthConnectionRequest',
    'OAuthConnectionSummary',
    'OAuthConnectionDetail',
    'OAuthConnection',
    'OAuthCredentials',  # Regular class for workflows (has is_expired, get_auth_header)
    'OAuthCredentialsModel',  # Pydantic model for API responses
    'OAuthCredentialsResponse',
    'OAuthCallbackRequest',
    'OAuthCallbackResponse',

    # MVP File Uploads
    'FileUploadRequest',
    'FileUploadResponse',

    # Workflow API Keys (User Story 3)
    'WorkflowKey',
    'WorkflowKeyCreateRequest',
    'WorkflowKeyResponse',

    # Async Execution (User Story 4)
    'AsyncExecution',
    'AsyncExecutionStatus',

    # CRON Scheduling (User Story 5)
    'CronSchedule',
    'CronScheduleCreateRequest',
    'CronScheduleUpdateRequest',
    'ScheduleInfo',
    'SchedulesListResponse',
    'CronValidationRequest',
    'CronValidationResponse',
    'ProcessSchedulesResponse',

    # Platform Branding (User Story 7)
    'BrandingSettings',
    'BrandingUpdateRequest',

    # Browser-based Code Editor
    'FileType',
    'FileMetadata',
    'FileContentRequest',
    'FileContentResponse',
    'FileConflictResponse',
    'SearchRequest',
    'SearchResult',
    'SearchResponse',

    # Script Execution
    'ScriptExecutionRequest',
    'ScriptExecutionResponse',

    # Package Management
    'InstallPackageRequest',
    'PackageInstallResponse',
    'InstalledPackage',
    'InstalledPackagesResponse',
    'PackageUpdate',
    'PackageUpdatesResponse',

    # GitHub Integration
    'GitFileStatus',
    'FileChange',
    'ConflictInfo',
    'GitHubConfigRequest',
    'GitHubConfigResponse',
    'GitHubRepoInfo',
    'GitHubReposResponse',
    'GitHubBranchInfo',
    'WorkspaceAnalysisResponse',
    'CreateRepoRequest',
    'CreateRepoResponse',
    'GitHubBranchesResponse',
    'CommitAndPushRequest',
    'CommitAndPushResponse',
    'PullFromGitHubResponse',
    'FileDiffRequest',
    'FileDiffResponse',
    'ResolveConflictRequest',
    'ResolveConflictResponse',
    'FetchFromGitHubResponse',
    'PushToGitHubRequest',
    'PushToGitHubResponse',
    'PullFromGitHubRequest',
    'PullFromGitHubResponse',
    'GitHubSyncRequest',
    'GitHubSyncResponse',
    'GitRefreshStatusResponse',
    'DiscardUnpushedCommitsResponse',
    'DiscardCommitRequest',
    'CommitHistoryResponse',
    'CommitInfo',

    # SDK Usage Scanning
    'SDKUsageType',
    'SDKUsageIssue',
    'WorkspaceScanRequest',
    'FileScanRequest',
    'WorkspaceScanResponse',

    # Common
    'ErrorResponse',

    # Helper functions
    'generate_entity_id',
    'parse_row_key',
    'parse_composite_row_key',
    'entity_to_model',
    'model_to_entity',
]


# ==================== ENUMS ====================

class ConfigType(str, Enum):
    """Configuration value types"""
    STRING = "string"
    INT = "int"
    BOOL = "bool"
    JSON = "json"
    SECRET = "secret"  # Value is encrypted


class ExecutionStatus(str, Enum):
    """Workflow execution status"""
    PENDING = "Pending"
    RUNNING = "Running"
    SUCCESS = "Success"
    FAILED = "Failed"
    TIMEOUT = "Timeout"
    COMPLETED_WITH_ERRORS = "CompletedWithErrors"
    CANCELLING = "Cancelling"
    CANCELLED = "Cancelled"


class RetryPolicy(BaseModel):
    """Retry policy configuration for workflow execution"""
    max_attempts: int = Field(3, ge=1, le=10, description="Total attempts including initial execution")
    backoff_seconds: int = Field(2, ge=1, description="Initial backoff duration in seconds")
    max_backoff_seconds: int = Field(60, ge=1, description="Maximum backoff cap in seconds")


class FormAccessLevel(str, Enum):
    """Form access control levels"""
    PUBLIC = "public"  # Future: unauthenticated access
    AUTHENTICATED = "authenticated"  # Any authenticated user
    ROLE_BASED = "role_based"  # Only users with assigned roles


class FormFieldType(str, Enum):
    """Form field types"""
    TEXT = "text"
    EMAIL = "email"
    NUMBER = "number"
    SELECT = "select"
    CHECKBOX = "checkbox"
    TEXTAREA = "textarea"
    # NEW MVP form component types (T012, T028)
    RADIO = "radio"
    DATETIME = "datetime"
    MARKDOWN = "markdown"
    HTML = "html"
    FILE = "file"


class DataProviderInputMode(str, Enum):
    """Data provider input configuration modes (T005)"""
    STATIC = "static"
    FIELD_REF = "fieldRef"
    EXPRESSION = "expression"


class IntegrationType(str, Enum):
    """Supported integration types"""
    MSGRAPH = "msgraph"
    HALOPSA = "halopsa"


class UserType(str, Enum):
    """User type - Platform admin or organization user"""
    PLATFORM = "PLATFORM"
    ORG = "ORG"


# ==================== ORGANIZATION MODELS ====================

class Organization(BaseModel):
    """Organization entity (response model)"""
    id: str = Field(..., description="Organization ID (GUID)")
    name: str = Field(..., min_length=1, max_length=200)
    domain: str | None = Field(
        None, description="Email domain for auto-provisioning users (e.g., 'acme.com')")
    is_active: bool = Field(default=True)
    created_at: datetime
    created_by: str
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CreateOrganizationRequest(BaseModel):
    """Request model for creating an organization"""
    name: str = Field(..., min_length=1, max_length=200)
    domain: str | None = Field(
        None, description="Email domain for auto-provisioning users (e.g., 'acme.com')")

    @field_validator('domain')
    @classmethod
    def validate_domain(cls, v):
        """Validate domain format (no @ symbol, just the domain)"""
        if v is not None:
            v = v.strip().lower()
            if '@' in v:
                raise ValueError("Domain should not include '@' symbol (e.g., use 'acme.com' not '@acme.com')")
            if not v or '.' not in v:
                raise ValueError("Domain must be a valid format (e.g., 'acme.com')")
        return v


class UpdateOrganizationRequest(BaseModel):
    """Request model for updating an organization"""
    name: str | None = Field(None, min_length=1, max_length=200)
    domain: str | None = Field(None, description="Email domain for auto-provisioning users")
    is_active: bool | None = None

    @field_validator('domain')
    @classmethod
    def validate_domain(cls, v):
        """Validate domain format (no @ symbol, just the domain)"""
        if v is not None:
            v = v.strip().lower()
            if '@' in v:
                raise ValueError("Domain should not include '@' symbol (e.g., use 'acme.com' not '@acme.com')")
            if not v or '.' not in v:
                raise ValueError("Domain must be a valid format (e.g., 'acme.com')")
        return v


# ==================== CONFIG MODELS ====================

class Config(BaseModel):
    """Configuration entity (global or org-specific)"""
    key: str
    value: Any = Field(..., description="Config value. For SECRET type, this will be '[SECRET]' in list responses.")
    type: ConfigType = ConfigType.STRING
    scope: Literal["GLOBAL", "org"] = Field(
        default="org", description="GLOBAL for MSP-wide or 'org' for org-specific")
    org_id: str | None = Field(
        None, description="Organization ID (only for org-specific config)")
    description: str | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None


class SetConfigRequest(BaseModel):
    """Request model for setting config"""
    key: str = Field(..., pattern=r"^[a-zA-Z0-9_]+$")
    value: str = Field(..., description="Config value. For SECRET type, this will be encrypted before storage.")
    type: ConfigType
    description: str | None = Field(None, description="Optional description of this config entry")


# ==================== INTEGRATION CONFIG MODELS ====================

class IntegrationConfig(BaseModel):
    """Integration configuration entity"""
    type: IntegrationType
    enabled: bool = Field(default=True)
    settings: dict[str, Any] = Field(...,
                                     description="Integration-specific settings")
    updated_at: datetime
    updated_by: str


class SetIntegrationConfigRequest(BaseModel):
    """Request model for setting integration config"""
    type: IntegrationType
    enabled: bool = Field(default=True)
    settings: dict[str, Any]

    @field_validator('settings')
    @classmethod
    def validate_settings(cls, v, info):
        """Validate integration-specific settings"""
        integration_type = info.data.get('type')

        if integration_type == IntegrationType.MSGRAPH:
            required_keys = {'tenant_id', 'client_id', 'client_secret_config_key'}
            if not required_keys.issubset(v.keys()):
                raise ValueError(
                    f"Microsoft Graph integration requires: {required_keys}")

        elif integration_type == IntegrationType.HALOPSA:
            required_keys = {'api_url', 'client_id', 'api_key_config_key'}
            if not required_keys.issubset(v.keys()):
                raise ValueError(
                    f"HaloPSA integration requires: {required_keys}")

        return v


# ==================== USER MODELS ====================

class User(BaseModel):
    """User entity"""
    id: str = Field(..., description="User ID from Azure AD")
    email: str
    display_name: str
    user_type: UserType = Field(
        default=UserType.PLATFORM, description="Platform admin or organization user")
    is_platform_admin: bool = Field(
        default=False, description="Whether user is platform admin")
    is_active: bool = Field(default=True)
    last_login: datetime | None = None
    created_at: datetime

    # NEW: Entra ID fields for enhanced authentication (T007)
    entra_user_id: str | None = Field(
        None, description="Azure AD user object ID (oid claim) for duplicate prevention")
    last_entra_id_sync: datetime | None = Field(
        None, description="Last synchronization timestamp from Azure AD")

    @field_validator('is_platform_admin')
    @classmethod
    def validate_platform_admin(cls, v, info):
        """Validate that only PLATFORM users can be admins"""
        user_type = info.data.get('user_type')
        if v and user_type != UserType.PLATFORM:
            raise ValueError("Only PLATFORM users can be admins")
        return v


class CreateUserRequest(BaseModel):
    """Request model for creating a user"""
    email: str = Field(..., description="User email address")
    display_name: str = Field(..., min_length=1, max_length=200, description="User display name")
    is_platform_admin: bool = Field(..., description="Whether user is a platform administrator")
    org_id: str | None = Field(None, description="Organization ID (required if is_platform_admin=false)")

    @model_validator(mode='after')
    def validate_org_requirement(self):
        """Validate that org_id is provided for non-platform-admin users"""
        if not self.is_platform_admin and not self.org_id:
            raise ValueError("org_id is required when is_platform_admin is false")
        if self.is_platform_admin and self.org_id:
            raise ValueError("org_id must be null when is_platform_admin is true")
        return self


class UpdateUserRequest(BaseModel):
    """Request model for updating a user"""
    display_name: str | None = Field(None, min_length=1, max_length=200, description="User display name")
    is_active: bool | None = Field(None, description="Whether user is active")
    is_platform_admin: bool | None = Field(None, description="Whether user is a platform administrator")
    org_id: str | None = Field(None, description="Organization ID (required when changing to is_platform_admin=false)")

    @model_validator(mode='after')
    def validate_org_requirement(self):
        """Validate that org_id is provided when demoting to non-platform-admin"""
        if self.is_platform_admin is False and not self.org_id:
            raise ValueError("org_id is required when setting is_platform_admin to false")
        return self


# ==================== AUTH & MFA MODELS ====================

class OAuthProviderInfo(BaseModel):
    """OAuth provider information for login page"""
    name: str
    display_name: str
    icon: str | None = None


class AuthStatusResponse(BaseModel):
    """
    Pre-login status response.

    Provides all information the client needs to render the login page:
    - Whether initial setup is required (no users exist)
    - Whether password login is available
    - Whether MFA is required for password login
    - Available OAuth/SSO providers
    """
    needs_setup: bool
    password_login_enabled: bool
    mfa_required_for_password: bool
    oauth_providers: list[OAuthProviderInfo]


class MFARequiredResponse(BaseModel):
    """Response when MFA verification is required."""
    mfa_required: bool = True
    mfa_token: str
    available_methods: list[str]
    expires_in: int = 300  # 5 minutes


class MFASetupRequiredResponse(BaseModel):
    """Response when MFA enrollment is required."""
    mfa_setup_required: bool = True
    mfa_token: str
    expires_in: int = 300  # 5 minutes


class MFAVerifyRequest(BaseModel):
    """Request to verify MFA code during login."""
    mfa_token: str
    code: str
    trust_device: bool = False
    device_name: str | None = None


class LoginResponse(BaseModel):
    """Unified login response that can be Token or MFA response."""
    # Token fields (when MFA not required or after MFA verification)
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    # MFA fields (when MFA required)
    mfa_required: bool = False
    mfa_setup_required: bool = False
    mfa_token: str | None = None
    available_methods: list[str] | None = None
    expires_in: int | None = None


class TokenRefresh(BaseModel):
    """Token refresh request model."""
    refresh_token: str


class UserResponse(BaseModel):
    """User response model."""
    id: str
    email: str
    name: str
    is_active: bool
    is_superuser: bool
    is_verified: bool


class MFASetupTokenRequest(BaseModel):
    """Request with MFA token for initial setup."""
    mfa_token: str


class MFASetupResponse(BaseModel):
    """MFA setup response with secret."""
    secret: str
    qr_code_uri: str
    provisioning_uri: str
    issuer: str
    account_name: str


class MFAEnrollVerifyRequest(BaseModel):
    """Request to verify MFA during initial enrollment."""
    mfa_token: str
    code: str


class MFAEnrollVerifyResponse(BaseModel):
    """Response after completing MFA enrollment."""
    success: bool
    recovery_codes: list[str]
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class OAuthLoginRequest(BaseModel):
    """OAuth/SSO login request model."""
    email: EmailStr
    name: str
    provider: str


# ==================== ROLE MODELS ====================

class Role(BaseModel):
    """Role entity for organization users"""
    id: str = Field(..., description="Role ID (GUID)")
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    is_active: bool = Field(default=True)
    created_by: str
    created_at: datetime
    updated_at: datetime


class CreateRoleRequest(BaseModel):
    """Request model for creating a role"""
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None


class UpdateRoleRequest(BaseModel):
    """Request model for updating a role"""
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None


class UserRole(BaseModel):
    """User-to-Role assignment entity"""
    user_id: str
    role_id: str
    assigned_by: str
    assigned_at: datetime


class FormRole(BaseModel):
    """Form-to-Role access control entity"""
    form_id: str
    role_id: str
    assigned_by: str
    assigned_at: datetime


class AssignUsersToRoleRequest(BaseModel):
    """Request model for assigning users to a role"""
    user_ids: list[str] = Field(..., min_length=1,
                               description="List of user IDs to assign")


class AssignFormsToRoleRequest(BaseModel):
    """Request model for assigning forms to a role"""
    form_ids: list[str] = Field(..., min_length=1,
                               description="List of form IDs to assign")


class RoleUsersResponse(BaseModel):
    """Response model for getting users assigned to a role"""
    user_ids: list[str] = Field(..., description="List of user IDs assigned to the role")


class RoleFormsResponse(BaseModel):
    """Response model for getting forms assigned to a role"""
    form_ids: list[str] = Field(..., description="List of form IDs assigned to the role")


# ==================== PERMISSION MODELS ====================

class UserPermission(BaseModel):
    """User permission entity"""
    user_id: str
    org_id: str
    can_execute_workflows: bool = Field(default=False)
    can_manage_config: bool = Field(default=False)
    can_manage_forms: bool = Field(default=False)
    can_view_history: bool = Field(default=False)
    granted_by: str
    granted_at: datetime


class PermissionsData(BaseModel):
    """Permissions data for grant request"""
    can_execute_workflows: bool
    can_manage_config: bool
    can_manage_forms: bool
    can_view_history: bool


class GrantPermissionsRequest(BaseModel):
    """Request model for granting permissions"""
    user_id: str
    org_id: str
    permissions: PermissionsData


class UserRolesResponse(BaseModel):
    """Response model for getting roles assigned to a user"""
    role_ids: list[str] = Field(..., description="List of role IDs assigned to the user")


class UserFormsResponse(BaseModel):
    """Response model for getting forms accessible to a user"""
    user_type: UserType = Field(..., description="User type (PLATFORM or ORG)")
    has_access_to_all_forms: bool = Field(..., description="Whether user has access to all forms")
    form_ids: list[str] = Field(default_factory=list, description="List of form IDs user can access (empty if has_access_to_all_forms=true)")


# ==================== FORM MODELS ====================

class FormFieldValidation(BaseModel):
    """Form field validation rules"""
    pattern: str | None = None
    min: float | None = None
    max: float | None = None
    message: str | None = None


class DataProviderInputConfig(BaseModel):
    """Configuration for a single data provider input parameter (T006)"""
    mode: DataProviderInputMode
    value: str | None = None
    field_name: str | None = None
    expression: str | None = None

    @model_validator(mode='after')
    def validate_mode_data(self):
        """Ensure exactly one field is set based on mode"""
        if self.mode == DataProviderInputMode.STATIC:
            if not self.value:
                raise ValueError("value required for static mode")
            if self.field_name or self.expression:
                raise ValueError("only value should be set for static mode")
        elif self.mode == DataProviderInputMode.FIELD_REF:
            if not self.field_name:
                raise ValueError("field_name required for fieldRef mode")
            if self.value or self.expression:
                raise ValueError("only field_name should be set for fieldRef mode")
        elif self.mode == DataProviderInputMode.EXPRESSION:
            if not self.expression:
                raise ValueError("expression required for expression mode")
            if self.value or self.field_name:
                raise ValueError("only expression should be set for expression mode")
        return self


class FormField(BaseModel):
    """Form field definition"""
    name: str = Field(..., description="Parameter name for workflow")
    label: str | None = Field(
        None, description="Display label (optional for markdown/html types)")
    type: FormFieldType
    required: bool = Field(default=False)
    validation: dict[str, Any] | None = None
    data_provider: str | None = Field(
        None, description="Data provider name for dynamic options")
    data_provider_inputs: dict[str, DataProviderInputConfig] | None = Field(
        None, description="Input configurations for data provider parameters (T007)")
    default_value: Any | None = None
    placeholder: str | None = None
    help_text: str | None = None

    # NEW MVP fields (T012)
    visibility_expression: str | None = Field(
        None, description="JavaScript expression for conditional visibility (e.g., context.field.show === true)")
    options: list[dict[str, str]] | None = Field(
        None, description="Options for radio/select fields")
    allowed_types: list[str] | None = Field(
        None, description="Allowed MIME types for file uploads")
    multiple: bool | None = Field(
        None, description="Allow multiple file uploads")
    max_size_mb: int | None = Field(
        None, description="Maximum file size in MB")
    content: str | None = Field(
        None, description="Static content for markdown/HTML components")
    allow_as_query_param: bool | None = Field(
        None, description="Whether this field's value can be populated from URL query parameters")

    @model_validator(mode='after')
    def validate_field_requirements(self):
        """Validate field-specific requirements"""
        # data_provider_inputs requires data_provider (T007)
        if self.data_provider_inputs and not self.data_provider:
            raise ValueError("data_provider_inputs requires data_provider to be set")

        # label is required for non-display fields (markdown/html use content instead)
        display_only_types = {FormFieldType.MARKDOWN, FormFieldType.HTML}
        if self.type not in display_only_types and not self.label:
            raise ValueError(f"label is required for {self.type.value} fields")

        # content is required for markdown/html fields
        if self.type in display_only_types and not self.content:
            raise ValueError(f"content is required for {self.type.value} fields")

        return self


class FormSchema(BaseModel):
    """Form schema with field definitions"""
    fields: list[FormField] = Field(..., max_length=50,
                                    description="Max 50 fields per form")

    @field_validator('fields')
    @classmethod
    def validate_unique_names(cls, v):
        """Ensure field names are unique"""
        names = [field.name for field in v]
        if len(names) != len(set(names)):
            raise ValueError("Field names must be unique")
        return v


class Form(BaseModel):
    """Form entity (response model)"""
    id: str
    org_id: str = Field(..., description="Organization ID or 'GLOBAL'")
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    workflow_id: str | None = Field(None, description="Workflow ID (UUID) to execute when form is submitted")
    form_schema: FormSchema
    is_active: bool = Field(default=True)
    is_global: bool = Field(default=False)
    access_level: FormAccessLevel | None = Field(
        default=None, description="Access control level. Defaults to 'role_based' if not set.")
    created_by: str
    created_at: datetime
    updated_at: datetime

    # Optional launch params
    allowed_query_params: list[str] | None = Field(
        None, description="List of allowed query parameter names to inject into form context")
    default_launch_params: dict[str, Any] | None = Field(
        None, description="Default parameter values for workflow execution")


class CreateFormRequest(BaseModel):
    """Request model for creating a form"""
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    workflow_id: str = Field(..., description="Workflow ID (UUID) to execute when form is submitted")
    form_schema: FormSchema
    is_global: bool = Field(default=False)
    access_level: FormAccessLevel = Field(
        default=FormAccessLevel.ROLE_BASED, description="Access control level")

    # Optional launch params
    allowed_query_params: list[str] | None = Field(
        None, description="List of allowed query parameter names to inject into form context")
    default_launch_params: dict[str, Any] | None = Field(
        None, description="Default parameter values for workflow execution")


class UpdateFormRequest(BaseModel):
    """Request model for updating a form"""
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    workflow_id: str | None = Field(None, description="Workflow ID (UUID) to execute when form is submitted")
    form_schema: FormSchema | None = None
    is_active: bool | None = None
    access_level: FormAccessLevel | None = None

    # Optional launch params
    allowed_query_params: list[str] | None = Field(
        None, description="List of allowed query parameter names to inject into form context")
    default_launch_params: dict[str, Any] | None = Field(
        None, description="Default parameter values for workflow execution")


class FormExecuteRequest(BaseModel):
    """Request model for executing a form"""
    form_data: dict[str, Any] = Field(..., description="Form field values")


class FormStartupResponse(BaseModel):
    """Response model for form startup/launch workflow execution"""
    result: dict[str, Any] | list[Any] | str | None = Field(None, description="Workflow execution result")


# ==================== WORKFLOW EXECUTION MODELS ====================

class ExecutionLog(BaseModel):
    """Single log entry from workflow execution"""
    timestamp: str
    level: str  # debug, info, warning, error
    message: str
    data: dict[str, Any] | None = None


class WorkflowExecution(BaseModel):
    """Workflow execution entity"""
    execution_id: str
    workflow_name: str
    org_id: str | None = None  # Organization ID for display/filtering
    form_id: str | None = None
    executed_by: str
    executed_by_name: str  # Display name of user who executed
    status: ExecutionStatus
    input_data: dict[str, Any]
    result: dict[str, Any] | list[Any] | str | None = None  # Can be dict/list (JSON) or str (HTML/text)
    result_type: str | None = None  # How to render result (json, html, text)
    error_message: str | None = None
    duration_ms: int | None = None
    started_at: datetime | None = None  # May be None if not started yet
    completed_at: datetime | None = None
    logs: list[dict[str, Any]] | None = None  # Structured logger output (replaces old ExecutionLog format)
    variables: dict[str, Any] | None = None  # Runtime variables captured from execution scope
    # Resource metrics (admin only, null for non-admins)
    peak_memory_bytes: int | None = None
    cpu_total_seconds: float | None = None


class WorkflowExecutionRequest(BaseModel):
    """Request model for executing a workflow"""
    workflow_id: str | None = Field(None, description="UUID of the workflow to execute (required if code not provided)")
    input_data: dict[str, Any] = Field(default_factory=dict, description="Workflow input parameters")
    form_id: str | None = Field(None, description="Optional form ID that triggered this execution")
    transient: bool = Field(default=False, description="If true, skip database persistence (for code editor debugging)")
    code: str | None = Field(None, description="Optional: Python code to execute as script (base64 encoded). If provided, executes code instead of looking up workflow by ID.")
    script_name: str | None = Field(None, description="Optional: Name/identifier for the script (used for logging when code is provided)")

    @model_validator(mode='after')
    def validate_workflow_or_code(self) -> 'WorkflowExecutionRequest':
        """Ensure either workflow_id or code is provided"""
        if not self.workflow_id and not self.code:
            raise ValueError("Either 'workflow_id' or 'code' must be provided")
        return self


class WorkflowExecutionResponse(BaseModel):
    """Response model for workflow execution"""
    execution_id: str
    workflow_id: str | None = None
    workflow_name: str | None = None  # Display name from @workflow decorator
    status: ExecutionStatus
    result: dict[str, Any] | list[Any] | str | None = None  # Can be dict/list (JSON) or str (HTML/text)
    error: str | None = None
    error_type: str | None = None
    details: dict[str, Any] | None = None
    duration_ms: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    # Enhanced debugging output for code editor
    logs: list[dict[str, Any]] | None = None  # Structured logger output
    variables: dict[str, Any] | None = None  # Runtime variables from execution scope
    is_transient: bool = False  # Flag for editor executions (no DB persistence)


class ExecutionsListResponse(BaseModel):
    """Response model for listing workflow executions with pagination"""
    executions: list[WorkflowExecution] = Field(..., description="List of workflow executions")
    continuation_token: str | None = Field(None, description="Continuation token for next page (opaque, base64-encoded). Presence of token indicates more results available.")


class StuckExecutionsResponse(BaseModel):
    """Response model for stuck executions query"""
    executions: list[WorkflowExecution] = Field(..., description="List of stuck executions")
    count: int = Field(..., description="Number of stuck executions found")


class CleanupTriggeredResponse(BaseModel):
    """Response model for cleanup trigger operation"""
    cleaned: int = Field(..., description="Total number of executions cleaned up")
    pending: int = Field(..., description="Number of pending executions timed out")
    running: int = Field(..., description="Number of running executions timed out")
    failed: int = Field(..., description="Number of executions that failed to clean up")


# ==================== SYSTEM LOGS MODELS ====================

class SystemLog(BaseModel):
    """System log entry (platform events, not workflow executions)"""
    event_id: str = Field(..., description="Unique event ID (UUID)")
    timestamp: datetime = Field(..., description="When the event occurred (ISO 8601)")
    category: Literal["discovery", "organization", "user", "role", "config", "secret", "form", "oauth", "execution", "system", "error"] = Field(..., description="Event category")
    level: Literal["info", "warning", "error", "critical"] = Field(..., description="Event severity level")
    message: str = Field(..., description="Human-readable event description")
    executed_by: str = Field(..., description="User ID or 'System'")
    executed_by_name: str = Field(..., description="Display name or 'System'")
    details: dict[str, Any] | None = Field(None, description="Additional event-specific data")


class SystemLogsListResponse(BaseModel):
    """Response model for listing system logs with pagination"""
    logs: list[SystemLog] = Field(..., description="List of system log entries")
    continuation_token: str | None = Field(None, description="Continuation token for next page (opaque, base64-encoded)")


# ==================== METADATA MODELS ====================

class WorkflowParameter(BaseModel):
    """Workflow parameter metadata"""
    name: str
    type: str  # string, int, bool, etc.
    required: bool
    label: str | None = None
    data_provider: str | None = None
    default_value: Any | None = None
    help_text: str | None = None
    validation: dict[str, Any] | None = None
    description: str | None = None


class WorkflowMetadata(BaseModel):
    """Workflow metadata for discovery API"""
    # Unique identifier
    id: str = Field(..., description="Workflow UUID")

    # Required fields
    name: str = Field(..., min_length=1, pattern=r"^[a-z0-9_]+$", description="Workflow name (snake_case)")
    description: str | None = Field(None, description="Human-readable description")

    # Optional fields with defaults
    category: str = Field("General", description="Category for organization")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization and search")
    parameters: list[WorkflowParameter] = Field(default_factory=list, description="Workflow parameters")

    # Execution configuration
    execution_mode: Literal["sync", "async"] = Field("sync", description="Execution mode")
    timeout_seconds: int = Field(1800, ge=1, le=7200, description="Max execution time in seconds (default 30 min, max 2 hours)")

    # Retry and scheduling (for future use)
    retry_policy: RetryPolicy | None = Field(None, description="Retry configuration")
    schedule: str | None = Field(None, description="Cron expression for scheduled execution")

    # HTTP Endpoint configuration
    endpoint_enabled: bool = Field(False, description="Whether workflow is exposed as HTTP endpoint")
    allowed_methods: list[str] = Field(default_factory=lambda: ["POST"], description="Allowed HTTP methods")
    disable_global_key: bool = Field(False, description="If true, only workflow-specific API keys work")
    public_endpoint: bool = Field(False, description="If true, skip authentication for webhooks")

    # Source tracking
    source_file_path: str | None = Field(None, description="Full file path to the workflow source code")
    relative_file_path: str | None = Field(None, description="Workspace-relative file path with /workspace/ prefix (e.g., '/workspace/workflows/my_workflow.py')")


class DataProviderMetadata(BaseModel):
    """Data provider metadata from @data_provider decorator (T008)"""
    name: str
    description: str | None = None
    category: str = "General"
    cache_ttl_seconds: int = 300
    parameters: list[WorkflowParameter] = Field(default_factory=list, description="Input parameters from @param decorators")
    source_file_path: str | None = Field(None, description="Full file path to the data provider source code")
    relative_file_path: str | None = Field(None, description="Workspace-relative file path with /workspace/ prefix (e.g., '/workspace/data_providers/my_provider.py')")


class FormDiscoveryMetadata(BaseModel):
    """Lightweight form metadata for discovery endpoint"""
    id: str
    name: str
    workflow_id: str | None = None
    org_id: str
    is_active: bool
    is_global: bool
    access_level: FormAccessLevel | str | None = None
    created_at: datetime
    updated_at: datetime


class MetadataResponse(BaseModel):
    """Response model for /admin/workflow endpoint"""
    workflows: list[WorkflowMetadata] = Field(default_factory=list)
    data_providers: list[DataProviderMetadata] = Field(default_factory=list)
    forms: list[FormDiscoveryMetadata] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


# ==================== WORKFLOW VALIDATION MODELS ====================

class ValidationIssue(BaseModel):
    """A single validation error or warning"""
    line: int | None = Field(None, description="Line number where issue occurs (if applicable)")
    message: str = Field(..., description="Human-readable error or warning message")
    severity: Literal["error", "warning"] = Field(..., description="Severity level")


class WorkflowValidationRequest(BaseModel):
    """Request model for workflow validation endpoint"""
    path: str = Field(..., description="Relative workspace path to the workflow file")
    content: str | None = Field(None, description="File content to validate (if not provided, reads from disk)")


class WorkflowValidationResponse(BaseModel):
    """Response model for workflow validation endpoint"""
    valid: bool = Field(..., description="True if workflow is valid and will be discovered")
    issues: list[ValidationIssue] = Field(default_factory=list, description="List of errors and warnings")
    metadata: WorkflowMetadata | None = Field(None, description="Workflow metadata if valid")


# ==================== DATA PROVIDER RESPONSE MODELS ====================

class DataProviderRequest(BaseModel):
    """Request model for data provider endpoint (T009)"""
    org_id: str | None = Field(None, description="Organization ID for org-scoped providers")
    inputs: dict[str, Any] | None = Field(None, description="Input parameter values for data provider")
    no_cache: bool = Field(False, description="Bypass cache and fetch fresh data")


class DataProviderOption(BaseModel):
    """Data provider option item"""
    label: str
    value: str
    metadata: dict[str, Any] | None = None


class DataProviderResponse(BaseModel):
    """Response model for data provider endpoint"""
    provider: str = Field(..., description="Name of the data provider")
    options: list[DataProviderOption] = Field(..., description="List of options returned by the provider")
    cached: bool = Field(..., description="Whether this result was served from cache")
    cache_expires_at: str = Field(..., description="Cache expiration timestamp")


# ==================== SECRET MODELS ====================

class SecretListResponse(BaseModel):
    """Response model for listing secrets"""
    secrets: list[str] = Field(...,
                               description="List of secret names available in Key Vault")
    org_id: str | None = Field(
        None, description="Organization ID filter (if applied)")
    count: int = Field(..., description="Total number of secrets returned")


class SecretCreateRequest(BaseModel):
    """Request model for creating a secret"""
    org_id: str = Field(...,
                       description="Organization ID or 'GLOBAL' for platform-wide")
    secret_key: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$",
                           description="Secret key (alphanumeric, hyphens, underscores)")
    value: str = Field(..., min_length=1, description="Secret value")

    @field_validator('secret_key')
    @classmethod
    def validate_secret_key(cls, v):
        """Validate secret key follows naming conventions"""
        if len(v) > 100:
            raise ValueError("Secret key must be 100 characters or less")
        return v


class SecretUpdateRequest(BaseModel):
    """Request model for updating a secret"""
    value: str = Field(..., min_length=1, description="New secret value")


class SecretResponse(BaseModel):
    """Response model for secret operations"""
    name: str = Field(...,
                      description="Full secret name in Key Vault (e.g., org-123--api-key)")
    org_id: str = Field(..., description="Organization ID or 'GLOBAL'")
    secret_key: str = Field(..., description="Secret key portion")
    value: str | None = Field(
        None, description="Secret value (only shown immediately after create/update)")
    message: str = Field(..., description="Operation result message")


# ==================== HEALTH MODELS ====================

class HealthCheck(BaseModel):
    """Individual health check result"""
    service: str = Field(..., description="Display name of the service (e.g., 'API', 'Key Vault')")
    healthy: bool = Field(..., description="Whether the service is healthy")
    message: str = Field(..., description="Health check message")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional service-specific metadata")


class BasicHealthResponse(BaseModel):
    """Basic health check response (liveness check)"""
    status: Literal["healthy"] = Field(default="healthy", description="Health status (always healthy if API responds)")
    service: str = Field(default="Bifrost Integrations API", description="Service name")
    timestamp: str = Field(..., description="Health check timestamp (ISO 8601)")


class GeneralHealthResponse(BaseModel):
    """General health check response with multiple service checks"""
    status: Literal["healthy", "degraded", "unhealthy"] = Field(..., description="Overall system health status")
    service: str = Field(default="Bifrost Integrations API", description="Service name")
    timestamp: datetime = Field(..., description="Health check timestamp")
    checks: list[HealthCheck] = Field(..., description="Individual service health checks")


class KeyVaultHealthResponse(BaseModel):
    """Health check response for Azure Key Vault"""
    status: Literal["healthy", "degraded",
                    "unhealthy"] = Field(..., description="Health status")
    message: str = Field(..., description="Health status message")
    vault_url: str | None = Field(
        None, description="Key Vault URL being monitored")
    can_connect: bool = Field(...,
                             description="Whether connection to Key Vault succeeded")
    can_list_secrets: bool = Field(...,
                                 description="Whether listing secrets is permitted")
    can_get_secrets: bool = Field(...,
                                description="Whether reading secrets is permitted")
    secret_count: int | None = Field(
        None, description="Number of secrets in Key Vault (if accessible)")
    last_checked: datetime = Field(..., description="Timestamp of health check")


# ==================== OAUTH MODELS ====================

class OAuthCallbackRequest(BaseModel):
    """Request model for OAuth callback endpoint"""
    code: str = Field(..., description="Authorization code from OAuth provider")
    state: str | None = Field(None, description="State parameter for CSRF protection")


class OAuthCallbackResponse(BaseModel):
    """Response model for OAuth callback endpoint"""
    success: bool = Field(..., description="Whether the OAuth connection was successful")
    message: str = Field(..., description="Status message")
    status: str = Field(..., description="Connection status")
    connection_name: str = Field(..., description="Name of the OAuth connection")
    warning_message: str | None = Field(None, description="Warning message displayed to user (e.g., missing refresh token)")
    error_message: str | None = Field(None, description="Error message displayed to user")


class OAuthCredentials:
    """
    OAuth credentials object for workflows

    Provides access to OAuth access_token and refresh_token
    for making authenticated API calls to third-party services
    """

    def __init__(
        self,
        connection_name: str,
        access_token: str,
        token_type: str,
        expires_at: datetime,
        refresh_token: str | None = None,
        scopes: str = ""
    ):
        self.connection_name = connection_name
        self.access_token = access_token
        self.token_type = token_type
        self.expires_at = expires_at
        self.refresh_token = refresh_token
        self.scopes = scopes

    def is_expired(self) -> bool:
        """Check if access token is expired"""
        return datetime.utcnow() >= self.expires_at

    def get_auth_header(self) -> str:
        """Get formatted Authorization header value"""
        return f"{self.token_type} {self.access_token}"

    def __repr__(self) -> str:
        return f"<OAuthCredentials connection={self.connection_name} expires_at={self.expires_at}>"


# ==================== DASHBOARD MODELS ====================

class ExecutionStats(BaseModel):
    """Execution statistics for dashboard"""
    total_executions: int
    success_count: int
    failed_count: int
    running_count: int
    pending_count: int
    success_rate: float
    avg_duration_seconds: float


class RecentFailure(BaseModel):
    """Recent failed execution info"""
    execution_id: str
    workflow_name: str
    error_message: str | None
    started_at: str | None


class DashboardMetricsResponse(BaseModel):
    """Dashboard metrics response"""
    workflow_count: int
    data_provider_count: int
    form_count: int
    execution_stats: ExecutionStats
    recent_failures: list[RecentFailure]


class PlatformMetricsSnapshot(BaseModel):
    """
    Platform metrics snapshot response.

    Pre-computed metrics for instant dashboard loads.
    Refreshed by scheduler every 1-5 minutes.
    """
    # Entity counts
    workflow_count: int
    form_count: int
    data_provider_count: int
    organization_count: int
    user_count: int
    # Execution stats (all time)
    total_executions: int
    total_success: int
    total_failed: int
    # Execution stats (last 24 hours)
    executions_24h: int
    success_24h: int
    failed_24h: int
    # Current state
    running_count: int
    pending_count: int
    # Performance (last 24 hours)
    avg_duration_ms_24h: int
    total_memory_bytes_24h: int
    total_cpu_seconds_24h: float
    # Success rates
    success_rate_all_time: float
    success_rate_24h: float
    # Timestamp
    refreshed_at: str


class DailyMetricsEntry(BaseModel):
    """Single day's execution metrics."""
    date: str
    organization_id: str | None = None
    organization_name: str | None = None
    # Counts
    execution_count: int
    success_count: int
    failed_count: int
    timeout_count: int
    cancelled_count: int
    # Duration
    avg_duration_ms: int
    max_duration_ms: int
    # Resources
    peak_memory_bytes: int
    total_memory_bytes: int
    peak_cpu_seconds: float
    total_cpu_seconds: float


class DailyMetricsResponse(BaseModel):
    """Response for daily execution metrics trends."""
    days: list[DailyMetricsEntry]
    total_days: int


class OrganizationMetricsSummary(BaseModel):
    """Summary metrics for a single organization."""
    organization_id: str
    organization_name: str
    # Counts
    total_executions: int
    success_count: int
    failed_count: int
    success_rate: float
    # Resources
    total_memory_bytes: int
    total_cpu_seconds: float
    avg_duration_ms: int


class OrganizationMetricsResponse(BaseModel):
    """Response for organization metrics breakdown."""
    organizations: list[OrganizationMetricsSummary]
    total_organizations: int


class ResourceMetricsEntry(BaseModel):
    """Resource usage metrics for a time period."""
    date: str
    # Memory
    peak_memory_bytes: int
    total_memory_bytes: int
    avg_memory_bytes: int
    # CPU
    peak_cpu_seconds: float
    total_cpu_seconds: float
    avg_cpu_seconds: float
    # Execution count for context
    execution_count: int


class ResourceMetricsResponse(BaseModel):
    """Response for resource usage trends."""
    days: list[ResourceMetricsEntry]
    total_days: int


class WorkflowMetricsSummary(BaseModel):
    """Aggregated metrics for a single workflow."""
    workflow_name: str
    total_executions: int
    success_count: int
    failed_count: int
    success_rate: float
    avg_memory_bytes: int
    avg_duration_ms: int
    avg_cpu_seconds: float
    peak_memory_bytes: int
    max_duration_ms: int


class WorkflowMetricsResponse(BaseModel):
    """Response for workflow metrics aggregations."""
    workflows: list[WorkflowMetricsSummary]
    total_workflows: int
    sort_by: str
    days: int


# ==================== LIST RESPONSE MODELS ====================

# List Response Models removed - Deprecated in favor of returning bare arrays


# ==================== MVP FILE UPLOAD MODELS (T027, T028) ====================

class FileUploadRequest(BaseModel):
    """Request model for generating file upload SAS URL"""
    file_name: str = Field(..., description="Original file name")
    content_type: str = Field(..., description="MIME type of the file")
    file_size: int = Field(..., description="File size in bytes")

class UploadedFileMetadata(BaseModel):
    """Metadata for uploaded file that workflows can use to access the file"""
    name: str = Field(..., description="Original file name")
    container: str = Field(..., description="Blob storage container name (e.g., 'uploads')")
    path: str = Field(..., description="Blob path within container")
    content_type: str = Field(..., description="MIME type of the file")
    size: int = Field(..., description="File size in bytes")

class FileUploadResponse(BaseModel):
    """Response model for file upload SAS URL generation"""
    upload_url: str = Field(..., description="URL for direct upload")
    blob_uri: str = Field(..., description="Final file URI")
    expires_at: str = Field(..., description="Token expiration timestamp (ISO format)")
    file_metadata: UploadedFileMetadata = Field(..., description="Metadata for accessing the uploaded file in workflows")


# ==================== WORKFLOW API KEYS (T004, T032, T033, T034 - User Story 3) ====================

class WorkflowKey(BaseModel):
    """Workflow API Key for HTTP access without user authentication"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique key ID")
    hashed_key: str = Field(..., description="SHA-256 hash of the API key")
    workflow_id: str | None = Field(None, description="Workflow-specific key, or None for global access")
    created_by: str = Field(..., description="User email who created the key")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: datetime | None = None
    revoked: bool = Field(default=False)
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    expires_at: datetime | None = Field(None, description="Optional expiration timestamp")
    description: str | None = Field(None, description="Optional key description")
    disable_global_key: bool = Field(default=False, description="If true, workflow opts out of global API keys")

class WorkflowKeyCreateRequest(BaseModel):
    """Request model for creating a workflow API key"""
    workflow_name: str | None = Field(None, description="Workflow-specific key, or None for global")
    expires_in_days: int | None = Field(None, description="Days until key expires (default: no expiration)")
    description: str | None = Field(None, description="Optional key description")
    disable_global_key: bool = Field(default=False, description="If true, workflow opts out of global API keys")

class WorkflowKeyResponse(BaseModel):
    """Response model for workflow key (includes raw key on creation only)"""
    id: str
    raw_key: str | None = Field(None, description="Raw API key (only returned on creation)")
    masked_key: str | None = Field(None, description="Last 4 characters for display")
    workflow_name: str | None = None
    created_by: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked: bool
    expires_at: datetime | None = None
    description: str | None = None
    disable_global_key: bool = Field(default=False, description="If true, workflow opts out of global API keys")

# ==================== ASYNC EXECUTION (T004, T042, T043 - User Story 4) ====================

class AsyncExecutionStatus(str, Enum):
    """Async execution status values"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class AsyncExecution(BaseModel):
    """Async workflow execution tracking"""
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = Field(..., description="Workflow name to execute")
    status: AsyncExecutionStatus = Field(default=AsyncExecutionStatus.QUEUED)
    parameters: dict[str, Any] = Field(default_factory=dict, description="Workflow input parameters")
    context: dict[str, Any] = Field(default_factory=dict, description="Execution context (org scope, user)")
    result: Any | None = Field(None, description="Workflow result (for small results)")
    result_blob_uri: str | None = Field(None, description="Blob URI for large results (>32KB)")
    error: str | None = Field(None, description="Error message if failed")
    error_details: dict[str, Any] | None = Field(None, description="Detailed error information")
    queued_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = Field(None, description="Execution duration in milliseconds")


# ==================== CRON SCHEDULING (T004, T052, T053 - User Story 5) ====================

class CronSchedule(BaseModel):
    """CRON schedule configuration for automatic workflow execution"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = Field(..., description="Workflow name to execute on schedule")
    cron_expression: str = Field(..., description="Standard CRON expression (e.g., '0 2 * * *')")
    human_readable: str | None = Field(None, description="Human-readable schedule description")
    enabled: bool = Field(default=True)
    parameters: dict[str, Any] = Field(default_factory=dict, description="Default parameters for execution")
    next_run_at: datetime = Field(..., description="Next scheduled execution time")
    last_run_at: datetime | None = None
    last_execution_id: str | None = Field(None, description="ID of last execution")
    created_by: str = Field(..., description="User email who created the schedule")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class CronScheduleCreateRequest(BaseModel):
    """Request model for creating a CRON schedule"""
    workflow_id: str = Field(..., description="Workflow name to schedule")
    cron_expression: str = Field(..., description="CRON expression (e.g., '0 2 * * *' for 2am daily)")
    parameters: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = Field(default=True)

    @field_validator('cron_expression')
    @classmethod
    def validate_cron_expression(cls, v):
        """Validate CRON expression format"""
        from croniter import croniter
        if not croniter.is_valid(v):
            raise ValueError(f"Invalid CRON expression: {v}")
        return v

class CronScheduleUpdateRequest(BaseModel):
    """Request model for updating a CRON schedule"""
    cron_expression: str | None = None
    parameters: dict[str, Any] | None = None
    enabled: bool | None = None


class ScheduleInfo(BaseModel):
    """Information about a scheduled workflow for display"""
    workflow_name: str = Field(..., description="Internal workflow name/identifier")
    workflow_description: str = Field(..., description="Display name of the workflow")
    cron_expression: str = Field(..., description="CRON expression")
    human_readable: str = Field(..., description="Human-readable schedule (e.g., 'Every day at 2:00 AM')")
    next_run_at: datetime | None = Field(None, description="Next scheduled execution time")
    last_run_at: datetime | None = Field(None, description="Last execution time")
    last_execution_id: str | None = Field(None, description="ID of last execution")
    execution_count: int = Field(0, description="Total number of times this schedule has been triggered")
    enabled: bool = Field(True, description="Whether this schedule is currently active")
    validation_status: Literal["valid", "warning", "error"] | None = Field(None, description="Validation status of the CRON expression")
    validation_message: str | None = Field(None, description="Validation message for warning/error statuses")
    is_overdue: bool = Field(False, description="Whether the schedule is overdue by more than 6 minutes")


class SchedulesListResponse(BaseModel):
    """Response model for listing scheduled workflows"""
    schedules: list[ScheduleInfo] = Field(..., description="List of scheduled workflows")
    total_count: int = Field(..., description="Total number of scheduled workflows")


class CronValidationRequest(BaseModel):
    """Request model for CRON validation"""
    expression: str = Field(..., description="CRON expression to validate")


class CronValidationResponse(BaseModel):
    """Response model for CRON validation"""
    valid: bool = Field(..., description="Whether the CRON expression is valid")
    human_readable: str = Field(..., description="Human-readable description")
    next_runs: list[str] | None = Field(None, description="Next 5 execution times (ISO format)")
    interval_seconds: int | None = Field(None, description="Seconds between executions")
    warning: str | None = Field(None, description="Warning message for too-frequent schedules")
    error: str | None = Field(None, description="Error message for invalid expressions")


class ProcessSchedulesResponse(BaseModel):
    """Response model for processing due schedules"""
    total: int = Field(..., description="Total number of scheduled workflows")
    due: int = Field(..., description="Number of schedules that were due")
    executed: int = Field(..., description="Number of schedules successfully executed")
    failed: int = Field(..., description="Number of schedules that failed to execute")
    errors: list[dict[str, str]] = Field(default_factory=list, description="List of error details")


# ==================== PLATFORM BRANDING (T004, T071 - User Story 7) ====================

class BrandingSettings(BaseModel):
    """Global platform branding configuration"""
    square_logo_url: str | None = Field(None, description="Square logo URL (for icons, 1:1 ratio)")
    rectangle_logo_url: str | None = Field(None, description="Rectangle logo URL (for headers, 16:9 ratio)")
    primary_color: str | None = Field(None, description="Primary brand color (hex format, e.g., #FF5733)")

    @field_validator('primary_color')
    @classmethod
    def validate_hex_color(cls, v):
        """Validate hex color format"""
        if v is None:
            return v
        if not v.startswith('#') or len(v) not in [4, 7]:
            raise ValueError("Primary color must be a valid hex color (e.g., #FFF or #FF5733)")
        try:
            int(v[1:], 16)
        except ValueError:
            raise ValueError("Primary color must be a valid hex color")
        return v

class BrandingUpdateRequest(BaseModel):
    """Request model for updating primary color only - logos use POST /logo/{type}"""
    primary_color: str | None = Field(None, description="Primary color (hex code, e.g., #0066CC)")


# ==================== ERROR MODEL ====================

class ErrorResponse(BaseModel):
    """API error response"""
    error: str = Field(..., description="Error code or type")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = None


# ==================== HELPER FUNCTIONS ====================


def generate_entity_id() -> str:
    """
    Generate UUID for entity IDs.

    Returns:
        UUID string (e.g., "550e8400-e29b-41d4-a716-446655440000")
    """
    return str(uuid.uuid4())


def parse_row_key(row_key: str) -> tuple[str, str]:
    """
    Parse 'type:id' row keys.

    Examples:
        "form:7c9e6679-7425-40de-944b-e07fc1f90ae7" → ("form", "7c9e6679-7425-40de-944b-e07fc1f90ae7")
        "config:workflow_key" → ("config", "workflow_key")
        "execution:9999999999999_uuid" → ("execution", "9999999999999_uuid")

    Args:
        row_key: Row key string

    Returns:
        Tuple of (entity_type, entity_id)
    """
    parts = row_key.split(':', 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def parse_composite_row_key(row_key: str, expected_parts: int) -> list[str]:
    """
    Parse multi-part row keys like 'assignedrole:role_uuid:user_id'.

    Examples:
        "assignedrole:a3b2c1d4-...:user-456" → ["assignedrole", "a3b2c1d4-...", "user-456"]
        "formrole:7c9e6679-...:a3b2c1d4-..." → ["formrole", "7c9e6679-...", "a3b2c1d4-..."]

    Args:
        row_key: Row key string
        expected_parts: Expected number of parts

    Returns:
        List of row key parts

    Raises:
        ValueError: If row key doesn't have expected number of parts
    """
    parts = row_key.split(':')
    if len(parts) != expected_parts:
        raise ValueError(f"Expected {expected_parts} parts in row key, got {len(parts)}: {row_key}")
    return parts


def entity_to_model(entity: dict, model_class: type[BaseModel]) -> BaseModel:
    """
    Convert Table Storage entity to Pydantic model.
    Handles composite row keys (type:uuid or type:id1:id2).

    Args:
        entity: Entity dictionary from Table Storage
        model_class: Pydantic model class to convert to

    Returns:
        Instance of the Pydantic model
    """
    # Remove Azure Table Storage metadata fields
    clean_entity = {k: v for k, v in entity.items() if not k.startswith(
        'odata') and k not in ['PartitionKey', 'RowKey', 'Timestamp', 'etag']}

    # Extract ID from row key (e.g., "form:7c9e6679-..." → "7c9e6679-...")
    if 'id' in model_class.model_fields and 'RowKey' in entity:
        row_key = entity['RowKey']
        entity_type, entity_id = parse_row_key(row_key)
        clean_entity['id'] = entity_id

    # Handle composite keys for junction tables (UserRole, FormRole, etc.)
    if 'user_id' in model_class.model_fields and 'role_id' in model_class.model_fields:
        # e.g., "userrole:user-123:a3b2c1d4-5678-90ab-cdef-1234567890ab"
        parts = parse_composite_row_key(entity['RowKey'], 3)
        clean_entity['user_id'] = parts[1]
        clean_entity['role_id'] = parts[2]  # UUID

    if 'form_id' in model_class.model_fields and 'role_id' in model_class.model_fields:
        # e.g., "formrole:form_uuid:role_uuid"
        parts = parse_composite_row_key(entity['RowKey'], 3)
        clean_entity['form_id'] = parts[1]  # UUID
        clean_entity['role_id'] = parts[2]  # UUID

    return model_class(**clean_entity)


def model_to_entity(
    model: BaseModel,
    partition_key: str,
    row_key: str,
    entity_type: str | None = None,
    generate_id: bool = False
) -> dict:
    """
    Convert Pydantic model to Table Storage entity.
    Constructs row key like 'type:uuid' if entity_type provided.
    Generates UUID if generate_id=True and model has no id.

    Args:
        model: Pydantic model instance
        partition_key: Partition key for the entity
        row_key: Row key for the entity (ignored if entity_type provided)
        entity_type: Optional entity type for composite row key construction
        generate_id: Whether to generate UUID if model has no id

    Returns:
        Entity dictionary ready for Table Storage
    """
    entity = model.model_dump()
    entity['PartitionKey'] = partition_key

    # Generate UUID if needed
    if generate_id and 'id' not in entity:
        entity['id'] = generate_entity_id()

    # Construct composite row key if entity_type provided
    if entity_type and 'id' in entity:
        entity['RowKey'] = f"{entity_type}:{entity['id']}"
        del entity['id']  # Remove id field, RowKey contains the UUID
    else:
        entity['RowKey'] = row_key

    return entity


# ==================== OAUTH CONNECTION MODELS ====================
# OAuth connection models for OAuth helper feature

# OAuth flow types (as string literals for validation)
OAuthFlowType = Literal["authorization_code", "client_credentials", "refresh_token"]

# OAuth connection status
OAuthStatus = Literal["not_connected", "waiting_callback", "testing", "connected", "completed", "failed"]


class CreateOAuthConnectionRequest(BaseModel):
    """
    Request model for creating a new OAuth connection
    POST /api/oauth/connections
    """
    connection_name: str = Field(
        ...,
        pattern=r"^[a-zA-Z0-9_-]+$",
        min_length=1,
        max_length=100,
        description="Unique connection identifier (alphanumeric, underscores, hyphens)"
    )
    name: str | None = Field(
        None,
        max_length=255,
        description="Display name for the connection (defaults to connection_name)"
    )
    description: str | None = Field(
        None,
        max_length=500,
        description="Optional description of this OAuth connection"
    )
    oauth_flow_type: OAuthFlowType = Field(
        ...,
        description="OAuth 2.0 flow type"
    )
    client_id: str = Field(
        ...,
        min_length=1,
        description="OAuth client ID (not sensitive)"
    )
    client_secret: str | None = Field(
        None,
        description="OAuth client secret (optional for PKCE flow, required for client_credentials, will be stored securely in Key Vault)"
    )
    authorization_url: str | None = Field(
        None,
        pattern=r"^https://",
        description="OAuth authorization endpoint URL (required for authorization_code, not used for client_credentials)"
    )
    token_url: str = Field(
        ...,
        pattern=r"^https://",
        description="OAuth token endpoint URL (must be HTTPS)"
    )
    scopes: str = Field(
        default="",
        description="Comma-separated list of OAuth scopes to request"
    )
    redirect_uri: str | None = Field(
        None,
        description="OAuth redirect URI (defaults to /oauth/callback/{connection_name})"
    )

    @classmethod
    def model_validate(cls, obj):
        # Convert empty string to None for optional fields
        if isinstance(obj, dict):
            if obj.get('client_secret') == '':
                obj['client_secret'] = None
            if obj.get('authorization_url') == '' or obj.get('authorization_url') is None:
                obj['authorization_url'] = None
        return super().model_validate(obj)

    @model_validator(mode='before')
    @classmethod
    def convert_empty_strings(cls, data):
        """Convert empty strings to None for optional fields before validation"""
        if isinstance(data, dict):
            if data.get('client_secret') == '':
                data['client_secret'] = None
            if data.get('authorization_url') == '':
                data['authorization_url'] = None
        return data

    @model_validator(mode='after')
    def validate_flow_requirements(self) -> 'CreateOAuthConnectionRequest':
        """Validate field requirements based on OAuth flow type"""
        if self.oauth_flow_type == 'client_credentials':
            # Client credentials: requires client_secret, doesn't need authorization_url
            if not self.client_secret:
                raise ValueError("client_secret is required for client_credentials flow")
            # Authorization URL is not used in client_credentials flow
            # We'll just ignore it if provided, or use a placeholder if needed

        elif self.oauth_flow_type == 'authorization_code':
            # Authorization code: requires authorization_url, client_secret is optional (PKCE)
            if not self.authorization_url:
                raise ValueError("authorization_url is required for authorization_code flow")

        return self


class UpdateOAuthConnectionRequest(BaseModel):
    """
    Request model for updating an OAuth connection
    PUT /api/oauth/connections/{connection_name}
    """
    name: str | None = Field(None, max_length=255, description="Display name")
    client_id: str | None = Field(None, min_length=1)
    client_secret: str | None = Field(None, min_length=1)
    authorization_url: str | None = Field(None, pattern=r"^https://")
    token_url: str | None = Field(None, pattern=r"^https://")
    scopes: list[str] | None = Field(None, description="List of OAuth scopes")

    @field_validator('scopes', mode='before')
    @classmethod
    def parse_scopes(cls, v):
        """Accept scopes as string (space or comma separated) or list."""
        if v is None:
            return None
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            # Handle both comma-separated and space-separated
            # First replace commas with spaces, then split
            return [s.strip() for s in v.replace(',', ' ').split() if s.strip()]
        return v


class OAuthConnectionSummary(BaseModel):
    """
    Summary model for OAuth connections (used in list responses)
    GET /api/oauth/connections

    Does not include sensitive fields or detailed configuration
    """
    connection_name: str
    name: str | None = Field(None, description="Display name for the connection")
    provider: str | None = Field(None, description="Provider identifier (same as connection_name)")
    description: str | None = None
    oauth_flow_type: OAuthFlowType
    status: OAuthStatus
    status_message: str | None = None
    expires_at: datetime | None = Field(
        None,
        description="When the current access token expires"
    )
    last_refresh_at: datetime | None = Field(
        None,
        description="Last successful token refresh"
    )
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class OAuthConnectionDetail(BaseModel):
    """
    Detailed model for OAuth connections (used in get/update responses)
    GET /api/oauth/connections/{connection_name}

    Includes configuration details but masks sensitive fields
    """
    connection_name: str
    name: str | None = Field(None, description="Display name for the connection")
    provider: str | None = Field(None, description="Provider identifier")
    description: str | None = None
    oauth_flow_type: OAuthFlowType
    client_id: str = Field(
        ...,
        description="OAuth client ID (safe to expose)"
    )
    authorization_url: str | None = Field(
        None,
        description="OAuth authorization endpoint (required for authorization_code, not used for client_credentials)"
    )
    token_url: str
    scopes: str
    redirect_uri: str = Field(
        ...,
        description="Callback URL for OAuth authorization"
    )

    # Status information
    status: OAuthStatus
    status_message: str | None = None
    expires_at: datetime | None = None
    last_refresh_at: datetime | None = None
    last_test_at: datetime | None = None

    # Metadata
    created_at: datetime
    created_by: str
    updated_at: datetime

    # NOTE: client_secret, access_token, refresh_token are NOT included
    # These are stored securely and never exposed in API responses

    model_config = ConfigDict(from_attributes=True)


class OAuthConnection(BaseModel):
    """
    Internal model representing full OAuth connection data
    Used for storage operations and business logic

    Includes references to secrets (not the actual secret values)
    """
    # Partition/Row Keys for Table Storage
    org_id: str = Field(..., description="Organization ID or 'GLOBAL'")
    connection_name: str = Field(
        ...,
        pattern=r"^[a-zA-Z0-9_-]+$",
        min_length=1,
        max_length=100
    )

    # OAuth Configuration
    description: str | None = Field(None, max_length=500)
    oauth_flow_type: OAuthFlowType
    client_id: str
    client_secret_config_key: str = Field(
        ...,
        description="Config key containing the encrypted client secret (oauth_{name}_client_secret)"
    )
    oauth_response_config_key: str = Field(
        ...,
        description="Config key containing the encrypted OAuth response (oauth_{name}_oauth_response)"
    )
    authorization_url: str | None = Field(
        None,
        pattern=r"^https://",
        description="OAuth authorization endpoint (required for authorization_code, not used for client_credentials)"
    )
    token_url: str = Field(..., pattern=r"^https://")
    scopes: str = ""
    redirect_uri: str = Field(
        ...,
        description="Callback URL: /api/oauth/callback/{connection_name}"
    )

    # Token metadata (not the actual tokens - those are in Config/KeyVault)
    token_type: str = "Bearer"
    expires_at: datetime | None = Field(
        None,
        description="When the current access token expires (copied from secret for quick checks)"
    )

    # Status tracking
    status: OAuthStatus
    status_message: str | None = None
    last_refresh_at: datetime | None = None
    last_test_at: datetime | None = None

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Helper methods

    def is_expired(self) -> bool:
        """
        Check if the current access token is expired

        Returns:
            True if token is expired or expires_at is not set
        """
        if not self.expires_at:
            return True
        return datetime.utcnow() >= self.expires_at

    def expires_soon(self, hours: int = 4) -> bool:
        """
        Check if the access token expires within the specified number of hours

        Args:
            hours: Number of hours to check (default: 4)

        Returns:
            True if token expires within the specified hours or is already expired
        """
        if not self.expires_at:
            return True
        threshold = datetime.utcnow() + timedelta(hours=hours)
        return self.expires_at <= threshold

    def to_summary(self) -> OAuthConnectionSummary:
        """Convert to summary response model"""
        return OAuthConnectionSummary(
            connection_name=self.connection_name,
            name=None,
            provider=self.connection_name,
            description=self.description,
            oauth_flow_type=self.oauth_flow_type,
            status=self.status,
            status_message=self.status_message,
            expires_at=self.expires_at,
            last_refresh_at=self.last_refresh_at,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def to_detail(self) -> OAuthConnectionDetail:
        """Convert to detail response model (masks secrets)"""
        return OAuthConnectionDetail(
            connection_name=self.connection_name,
            name=None,
            provider=self.connection_name,
            description=self.description,
            oauth_flow_type=self.oauth_flow_type,
            client_id=self.client_id,
            authorization_url=self.authorization_url,
            token_url=self.token_url,
            scopes=self.scopes,
            redirect_uri=self.redirect_uri,
            status=self.status,
            status_message=self.status_message,
            expires_at=self.expires_at,
            last_refresh_at=self.last_refresh_at,
            last_test_at=self.last_test_at,
            created_at=self.created_at,
            created_by=self.created_by,
            updated_at=self.updated_at,
        )

    model_config = ConfigDict(from_attributes=True)


class OAuthCredentialsModel(BaseModel):
    """
    OAuth credentials Pydantic model for API responses
    GET /api/oauth/credentials/{connection_name}

    Contains actual access token and refresh token for use in API calls
    This model is only exposed to authenticated workflow contexts

    Note: This is the Pydantic model for API responses. The regular OAuthCredentials
    class (line 839) is used for workflow consumption with is_expired() and get_auth_header() methods.
    """
    connection_name: str = Field(
        ...,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Connection identifier"
    )
    access_token: str = Field(
        ...,
        min_length=1,
        description="Current OAuth access token"
    )
    token_type: str = Field(
        default="Bearer",
        description="Token type (usually Bearer)"
    )
    expires_at: str = Field(
        ...,
        description="ISO 8601 timestamp when token expires"
    )
    refresh_token: str | None = Field(
        None,
        description="Refresh token if available"
    )
    scopes: str = Field(
        default="",
        description="Space-separated list of granted scopes"
    )

    model_config = ConfigDict(from_attributes=True)


class OAuthCredentialsResponse(BaseModel):
    """
    Response wrapper for OAuth credentials endpoint
    Includes connection status and metadata
    """
    connection_name: str
    credentials: OAuthCredentialsModel | None = Field(
        None,
        description="Credentials if connection is active, None if not connected"
    )
    status: OAuthStatus = Field(
        ...,
        description="Current connection status"
    )
    expires_at: str | None = Field(
        None,
        description="ISO 8601 timestamp when token expires"
    )

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Editor Models (Browser-Based Code Editor)
# ============================================================================

class FileType(str, Enum):
    """File or folder type"""
    FILE = "file"
    FOLDER = "folder"


class FileMetadata(BaseModel):
    """
    File or folder metadata
    Used in directory listing responses
    """
    path: str = Field(..., description="Relative path from /home/repo")
    name: str = Field(..., description="File or folder name")
    type: FileType = Field(..., description="File or folder")
    size: int | None = Field(None, description="Size in bytes (null for folders)")
    extension: str | None = Field(None, description="File extension (null for folders)")
    modified: str = Field(..., description="Last modified timestamp (ISO 8601)")
    isReadOnly: bool = Field(default=False, description="Whether file is read-only")

    model_config = ConfigDict(from_attributes=True)


class FileContentRequest(BaseModel):
    """Request to write file content"""
    path: str = Field(..., description="Relative path from /home/repo")
    content: str = Field(..., description="File content (plain text or base64 encoded)")
    encoding: str = Field(default="utf-8", description="Content encoding (utf-8 or base64)")
    expected_etag: str | None = Field(default=None, description="Expected ETag for conflict detection (optional)")

    model_config = ConfigDict(from_attributes=True)


class FileContentResponse(BaseModel):
    """Response with file content"""
    path: str = Field(..., description="Relative path from /home/repo")
    content: str = Field(..., description="File content")
    encoding: str = Field(..., description="Content encoding")
    size: int = Field(..., description="Content size in bytes")
    etag: str = Field(..., description="ETag for change detection")
    modified: str = Field(..., description="Last modified timestamp (ISO 8601)")

    model_config = ConfigDict(from_attributes=True)


class FileConflictResponse(BaseModel):
    """Response when file write encounters a conflict"""
    reason: Literal["content_changed", "path_not_found"] = Field(..., description="Type of conflict")
    message: str = Field(..., description="Human-readable conflict description")

    model_config = ConfigDict(from_attributes=True)


class SearchRequest(BaseModel):
    """Search query request"""
    query: str = Field(..., min_length=1, description="Search text or regex pattern")
    case_sensitive: bool = Field(default=False, description="Case-sensitive matching")
    is_regex: bool = Field(default=False, description="Treat query as regex")
    include_pattern: str | None = Field(default="**/*", description="Glob pattern for files to search")
    max_results: int = Field(default=1000, ge=1, le=10000, description="Maximum results to return")

    model_config = ConfigDict(from_attributes=True)


class SearchResult(BaseModel):
    """Single search match result"""
    file_path: str = Field(..., description="Relative path to file containing match")
    line: int = Field(..., ge=1, description="Line number (1-indexed)")
    column: int = Field(..., ge=0, description="Column number (0-indexed)")
    match_text: str = Field(..., description="The matched text")
    context_before: str | None = Field(None, description="Line before match")
    context_after: str | None = Field(None, description="Line after match")

    model_config = ConfigDict(from_attributes=True)


class SearchResponse(BaseModel):
    """Search results response"""
    query: str = Field(..., description="Original search query")
    total_matches: int = Field(..., description="Total matches found")
    files_searched: int = Field(..., description="Number of files searched")
    results: list[SearchResult] = Field(..., description="Array of search results")
    truncated: bool = Field(..., description="Whether results were truncated")
    search_time_ms: int = Field(..., description="Search duration in milliseconds")

    model_config = ConfigDict(from_attributes=True)


# ==================== SCRIPT EXECUTION MODELS ====================

class ScriptExecutionRequest(BaseModel):
    """Request model for executing a Python script"""
    code: str = Field(..., description="Python code to execute")
    timeout_seconds: int | None = Field(None, description="Optional timeout in seconds")


class ScriptExecutionResponse(BaseModel):
    """Response model for script execution"""
    execution_id: str = Field(..., description="Unique execution identifier")
    status: Literal["Success", "Failed"] = Field(..., description="Execution status")
    output: str = Field(..., description="Combined stdout/stderr output")
    result: dict[str, str] | None = Field(None, description="Execution result data")
    error: str | None = Field(None, description="Error message if execution failed")
    duration_ms: int = Field(..., description="Execution duration in milliseconds")
    started_at: datetime = Field(..., description="Execution start timestamp")
    completed_at: datetime = Field(..., description="Execution completion timestamp")


# ==================== PACKAGE MANAGEMENT MODELS ====================

class InstallPackageRequest(BaseModel):
    """Request model for installing a package"""
    package: str = Field(..., min_length=1, description="Package name to install")
    version: str | None = Field(None, description="Optional package version (e.g., '2.31.0')")

    model_config = ConfigDict(from_attributes=True)


class PackageInstallResponse(BaseModel):
    """Response model for package installation"""
    job_id: str = Field(..., description="Job ID for tracking installation progress")
    status: Literal["queued"] = Field(default="queued", description="Installation status")

    model_config = ConfigDict(from_attributes=True)


class InstalledPackage(BaseModel):
    """Installed package information"""
    name: str = Field(..., description="Package name")
    version: str = Field(..., description="Installed version")

    model_config = ConfigDict(from_attributes=True)


class InstalledPackagesResponse(BaseModel):
    """Response model for listing installed packages"""
    packages: list[InstalledPackage] = Field(..., description="List of installed packages")

    model_config = ConfigDict(from_attributes=True)


class PackageUpdate(BaseModel):
    """Package update information"""
    name: str = Field(..., description="Package name")
    current_version: str = Field(..., description="Currently installed version")
    latest_version: str = Field(..., description="Latest available version")

    model_config = ConfigDict(from_attributes=True)


class PackageUpdatesResponse(BaseModel):
    """Response model for checking package updates"""
    updates: list[PackageUpdate] = Field(..., description="List of available updates")

    model_config = ConfigDict(from_attributes=True)


# ==================== GITHUB INTEGRATION ====================


class GitFileStatus(str, Enum):
    """Git file status"""
    MODIFIED = "M"      # Modified file
    ADDED = "A"         # New file (untracked or staged)
    DELETED = "D"       # Deleted file
    UNTRACKED = "U"     # Untracked file
    CONFLICTED = "C"    # File with merge conflicts


class FileChange(BaseModel):
    """Represents a changed file in Git"""
    path: str = Field(..., description="Relative path from workspace root")
    status: GitFileStatus = Field(..., description="Git status of the file")
    additions: int | None = Field(None, description="Number of lines added")
    deletions: int | None = Field(None, description="Number of lines deleted")

    model_config = ConfigDict(from_attributes=True)


class ConflictInfo(BaseModel):
    """Information about conflicts in a file (no markers written to disk)"""
    file_path: str = Field(..., description="Relative path to conflicted file")
    current_content: str = Field(..., description="Local version of the file")
    incoming_content: str = Field(..., description="Remote version of the file")
    base_content: str | None = Field(None, description="Common ancestor version (if available)")

    model_config = ConfigDict(from_attributes=True)


class ValidateTokenRequest(BaseModel):
    """Request to validate GitHub token"""
    token: str = Field(..., description="GitHub personal access token to validate")

    model_config = ConfigDict(from_attributes=True)


class GitHubConfigRequest(BaseModel):
    """Request to configure GitHub integration - will always replace workspace with remote"""
    repo_url: str = Field(..., min_length=1, description="GitHub repository URL (e.g., https://github.com/user/repo)")
    auth_token: str = Field(..., description="GitHub personal access token")
    branch: str = Field(default="main", description="Branch to sync with")

    model_config = ConfigDict(from_attributes=True)


class GitHubConfigResponse(BaseModel):
    """Response after configuring GitHub"""
    configured: bool = Field(..., description="Whether GitHub is fully configured")
    token_saved: bool = Field(default=False, description="Whether a GitHub token has been validated and saved")
    repo_url: str | None = Field(None, description="Configured repository URL")
    branch: str | None = Field(None, description="Configured branch")
    backup_path: str | None = Field(None, description="Path to backup directory if workspace was backed up")

    model_config = ConfigDict(from_attributes=True)


class GitHubRepoInfo(BaseModel):
    """GitHub repository information"""
    name: str = Field(..., description="Repository name (owner/repo)")
    full_name: str = Field(..., description="Full repository name")
    description: str | None = Field(None, description="Repository description")
    url: str = Field(..., description="Repository URL")
    private: bool = Field(..., description="Whether repository is private")

    model_config = ConfigDict(from_attributes=True)


class DetectedRepoInfo(BaseModel):
    """Information about auto-detected existing repository"""
    full_name: str = Field(..., description="Repository full name (owner/repo)")
    branch: str = Field(..., description="Current branch")

    model_config = ConfigDict(from_attributes=True)


class GitHubReposResponse(BaseModel):
    """Response with list of GitHub repositories"""
    repositories: list[GitHubRepoInfo] = Field(..., description="List of accessible repositories")
    detected_repo: DetectedRepoInfo | None = Field(None, description="Auto-detected existing repository")

    model_config = ConfigDict(from_attributes=True)


class GitHubBranchInfo(BaseModel):
    """GitHub branch information"""
    name: str = Field(..., description="Branch name")
    protected: bool = Field(..., description="Whether branch is protected")
    commit_sha: str = Field(..., description="Latest commit SHA")

    model_config = ConfigDict(from_attributes=True)


class GitHubBranchesResponse(BaseModel):
    """Response with list of branches"""
    branches: list[GitHubBranchInfo] = Field(..., description="List of branches in repository")

    model_config = ConfigDict(from_attributes=True)


class WorkspaceAnalysisResponse(BaseModel):
    """Response with workspace analysis - simplified for replace-only strategy"""
    workspace_status: Literal["empty", "has_files_no_git", "is_git_repo", "is_different_git_repo"] = Field(
        ...,
        description="Current state of the workspace directory"
    )
    file_count: int = Field(..., description="Number of files in workspace (excluding .git)")
    existing_remote: str | None = Field(None, description="URL of existing Git remote (if any)")
    requires_confirmation: bool = Field(..., description="Whether user needs to confirm replacing workspace")
    backup_will_be_created: bool = Field(default=True, description="Indicates a backup will be created before replacing")

    model_config = ConfigDict(from_attributes=True)


class CreateRepoRequest(BaseModel):
    """Request to create a new GitHub repository"""
    name: str = Field(..., min_length=1, description="Repository name")
    description: str | None = Field(None, description="Repository description")
    private: bool = Field(default=True, description="Whether repository should be private")
    organization: str | None = Field(None, description="Organization name (if creating in an org)")

    model_config = ConfigDict(from_attributes=True)


class GitHubConfigEntity(BaseModel):
    """GitHub integration configuration stored in Config table"""
    status: Literal["disconnected", "token_saved", "configured"] = Field(
        ...,
        description="Integration status: disconnected (inactive), token_saved (validated), configured (ready)"
    )
    token_config_key: str | None = Field(None, description="Config key containing the encrypted GitHub token")
    repo_url: str | None = Field(None, description="Configured repository URL")
    production_branch: str | None = Field(None, description="Production branch to sync with")
    updated_at: datetime | None = Field(None, description="Last update timestamp")
    updated_by: str | None = Field(None, description="User who last updated configuration")

    model_config = ConfigDict(from_attributes=True)


class CreateRepoResponse(BaseModel):
    """Response after creating a new repository"""
    full_name: str = Field(..., description="Full repository name (owner/repo)")
    url: str = Field(..., description="Repository URL")
    clone_url: str = Field(..., description="HTTPS clone URL")

    model_config = ConfigDict(from_attributes=True)


class FetchFromGitHubResponse(BaseModel):
    """Response after fetching from remote"""
    success: bool = Field(..., description="Whether fetch was successful")
    commits_ahead: int = Field(default=0, description="Number of local commits ahead of remote")
    commits_behind: int = Field(default=0, description="Number of commits behind remote")
    error: str | None = Field(None, description="Error message if fetch failed")

    model_config = ConfigDict(from_attributes=True)


class CommitAndPushRequest(BaseModel):
    """Request to commit and push changes"""
    message: str = Field(..., min_length=1, description="Commit message")

    model_config = ConfigDict(from_attributes=True)


class CommitAndPushResponse(BaseModel):
    """Response after commit and push"""
    success: bool = Field(..., description="Whether operation succeeded")
    commit_sha: str | None = Field(None, description="SHA of created commit")
    files_committed: int = Field(..., description="Number of files committed")
    error: str | None = Field(None, description="Error message if operation failed")

    model_config = ConfigDict(from_attributes=True)


class PushToGitHubRequest(BaseModel):
    """Request to push to GitHub"""
    message: str | None = Field(None, description="Commit message")
    connection_id: str | None = Field(None, description="WebPubSub connection ID for streaming logs")

    model_config = ConfigDict(from_attributes=True)


class PushToGitHubResponse(BaseModel):
    """Response after pushing to GitHub"""
    success: bool = Field(..., description="Whether push succeeded")
    error: str | None = Field(None, description="Error message if push failed")

    model_config = ConfigDict(from_attributes=True)


class PullFromGitHubRequest(BaseModel):
    """Request to pull from GitHub"""
    connection_id: str | None = Field(None, description="WebPubSub connection ID for streaming logs")

    model_config = ConfigDict(from_attributes=True)


class PullFromGitHubResponse(BaseModel):
    """Response after pulling from GitHub"""
    success: bool = Field(..., description="Whether pull succeeded")
    updated_files: list[str] = Field(default_factory=list, description="List of updated file paths")
    conflicts: list[ConflictInfo] = Field(default_factory=list, description="List of conflicts (if any)")
    error: str | None = Field(None, description="Error message if pull failed")

    model_config = ConfigDict(from_attributes=True)


class GitHubSyncRequest(BaseModel):
    """Request to sync with GitHub (pull + push)"""
    connection_id: str | None = Field(None, description="WebPubSub connection ID for streaming logs")

    model_config = ConfigDict(from_attributes=True)


class GitHubSyncResponse(BaseModel):
    """Response after queueing a git sync job"""
    job_id: str = Field(..., description="Job ID for tracking the sync operation")
    status: str = Field(..., description="Job status (queued, processing, completed, failed)")

    model_config = ConfigDict(from_attributes=True)


class GitRefreshStatusResponse(BaseModel):
    """
    Unified response after fetching and getting complete Git status.
    This combines fetch + status + commit history into a single response.
    """
    success: bool = Field(..., description="Whether refresh was successful")
    initialized: bool = Field(..., description="Whether Git repository is initialized")
    configured: bool = Field(..., description="Whether GitHub integration is configured")
    current_branch: str | None = Field(None, description="Current branch name")

    # Local changes
    changed_files: list[FileChange] = Field(default_factory=list, description="List of locally changed files")
    conflicts: list[ConflictInfo] = Field(default_factory=list, description="List of merge conflicts")
    merging: bool = Field(default=False, description="Whether repository is in merge state (MERGE_HEAD exists)")

    # Remote sync status
    commits_ahead: int = Field(default=0, description="Number of local commits ahead of remote (ready to push)")
    commits_behind: int = Field(default=0, description="Number of commits behind remote (ready to pull)")

    # Commit history
    commit_history: list['CommitInfo'] = Field(default_factory=list, description="Recent commit history with pushed/unpushed status")

    # Metadata
    last_synced: str = Field(..., description="ISO timestamp of when sync was performed")
    error: str | None = Field(None, description="Error message if sync failed")

    model_config = ConfigDict(from_attributes=True)


class DiscardUnpushedCommitsResponse(BaseModel):
    """Response after discarding unpushed commits"""
    success: bool = Field(..., description="Whether discard was successful")
    discarded_commits: list['CommitInfo'] = Field(default_factory=list, description="List of commits that were discarded")
    new_head: str | None = Field(None, description="New HEAD commit SHA after discard")
    error: str | None = Field(None, description="Error message if operation failed")

    model_config = ConfigDict(from_attributes=True)


class DiscardCommitRequest(BaseModel):
    """Request to discard a specific commit and all newer commits"""
    commit_sha: str = Field(..., min_length=1, description="SHA of the commit to discard (this commit and all newer commits will be discarded)")

    model_config = ConfigDict(from_attributes=True)


class FileDiffRequest(BaseModel):
    """Request to get file diff"""
    file_path: str = Field(..., min_length=1, description="Relative path to file")

    model_config = ConfigDict(from_attributes=True)


class FileDiffResponse(BaseModel):
    """Response with file diff information"""
    file_path: str = Field(..., description="Relative path to file")
    old_content: str | None = Field(None, description="Previous file content (None if new file)")
    new_content: str = Field(..., description="Current file content")
    additions: int = Field(..., description="Number of lines added")
    deletions: int = Field(..., description="Number of lines deleted")

    model_config = ConfigDict(from_attributes=True)


class ResolveConflictRequest(BaseModel):
    """Request to resolve a conflict"""
    file_path: str = Field(..., min_length=1, description="Relative path to conflicted file")
    resolution: Literal["current", "incoming", "both", "manual"] = Field(..., description="How to resolve conflict")
    manual_content: str | None = Field(None, description="Manual resolution content (required if resolution='manual')")

    @model_validator(mode='after')
    def validate_manual_content(self):
        if self.resolution == "manual" and not self.manual_content:
            raise ValueError("manual_content is required when resolution is 'manual'")
        return self

    model_config = ConfigDict(from_attributes=True)


class ResolveConflictResponse(BaseModel):
    """Response after resolving conflict"""
    success: bool = Field(..., description="Whether resolution succeeded")
    file_path: str = Field(..., description="Path to resolved file")
    remaining_conflicts: int = Field(..., description="Number of remaining conflicts in file")

    model_config = ConfigDict(from_attributes=True)


class CommitInfo(BaseModel):
    """Information about a single commit"""
    sha: str = Field(..., description="Commit SHA")
    message: str = Field(..., description="Commit message")
    author: str = Field(..., description="Commit author")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    is_pushed: bool = Field(..., description="Whether commit is pushed to remote")

    model_config = ConfigDict(from_attributes=True)


class CommitHistoryResponse(BaseModel):
    """Response with commit history and pagination"""
    commits: list[CommitInfo] = Field(default_factory=list, description="List of commits (newest first)")
    total_commits: int = Field(..., description="Total number of commits in the entire history")
    has_more: bool = Field(..., description="Whether there are more commits to load")

    model_config = ConfigDict(from_attributes=True)


# ==================== SDK USAGE SCANNING ====================

class SDKUsageType(str, Enum):
    """Type of SDK usage"""
    CONFIG = "config"
    SECRET = "secret"
    OAUTH = "oauth"


class SDKUsageIssue(BaseModel):
    """
    Represents a missing SDK dependency found in a workflow file.

    This is returned when scanning workspace files for config.get(),
    secrets.get(), or oauth.get_token() calls that reference
    non-existent configurations.
    """
    file_path: str = Field(..., description="Relative path to the file in workspace")
    file_name: str = Field(..., description="Name of the file")
    type: SDKUsageType = Field(..., description="Type of SDK call (config, secret, oauth)")
    key: str = Field(..., description="The missing key/provider name")
    line_number: int = Field(..., description="Line number where the call is made")

    model_config = ConfigDict(from_attributes=True)


class WorkspaceScanRequest(BaseModel):
    """Request to scan workspace for SDK usage issues"""
    # No fields needed - scans entire workspace
    pass

    model_config = ConfigDict(from_attributes=True)


class FileScanRequest(BaseModel):
    """Request to scan a single file for SDK usage issues"""
    file_path: str = Field(..., min_length=1, description="Relative path to file in workspace")
    content: str | None = Field(None, description="Optional file content (if not provided, reads from disk)")

    model_config = ConfigDict(from_attributes=True)


class WorkspaceScanResponse(BaseModel):
    """Response from scanning workspace for SDK usage and form validation issues"""
    issues: list[SDKUsageIssue] = Field(default_factory=list, description="List of SDK usage issues found")
    scanned_files: int = Field(..., description="Number of Python files scanned")
    # Form validation issues (added to existing response for unified scanning)
    form_issues: list['FormValidationIssue'] = Field(
        default_factory=list, description="List of form validation issues found")
    scanned_forms: int = Field(default=0, description="Number of form files scanned")
    valid_forms: int = Field(default=0, description="Number of valid forms loaded")

    model_config = ConfigDict(from_attributes=True)


# ==================== FORM VALIDATION SCANNING ====================

class FormValidationIssue(BaseModel):
    """
    Represents a validation error found when loading a form definition.

    This is returned when scanning workspace form files (*.form.json, form.json)
    that have schema validation errors preventing them from loading.
    """
    file_path: str = Field(..., description="Relative path to the form file in workspace")
    file_name: str = Field(..., description="Name of the form file")
    form_name: str | None = Field(None, description="Name of the form if parseable")
    error_message: str = Field(..., description="Validation error message")
    field_name: str | None = Field(None, description="Name of the field with the error, if applicable")
    field_index: int | None = Field(None, description="Index of the field with the error, if applicable")

    model_config = ConfigDict(from_attributes=True)


class FormScanResponse(BaseModel):
    """Response from scanning workspace for form validation issues"""
    issues: list[FormValidationIssue] = Field(default_factory=list, description="List of form validation issues found")
    scanned_forms: int = Field(..., description="Number of form files scanned")
    valid_forms: int = Field(..., description="Number of valid forms loaded")

    model_config = ConfigDict(from_attributes=True)
