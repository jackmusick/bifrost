"""
Pydantic Schemas for Bifrost API

These schemas define the API contract for request/response validation.
Uses inheritance to minimize field duplication:

- Base: Shared fields (defined once)
- Create: For POST requests (inherits Base, adds create-specific fields)
- Update: For PATCH/PUT requests (all fields optional)
- Public: For responses (inherits Base, adds read-only fields like id, timestamps)

Usage with ORM models:
    user_db = await db.get(User, id)
    return UserPublic.model_validate(user_db)  # Auto-converts matching fields
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer, field_validator, model_validator

from shared.models import FormSchema, FormField, FormFieldType
from src.models.enums import (
    ConfigType,
    ExecutionStatus,
    FormAccessLevel,
    UserType,
)


# =============================================================================
# Organization Schemas
# =============================================================================


class OrganizationBase(BaseModel):
    """Shared organization fields."""
    name: str = Field(max_length=255)
    domain: str | None = Field(default=None, max_length=255)
    is_active: bool = Field(default=True)
    settings: dict = Field(default_factory=dict)


class OrganizationCreate(OrganizationBase):
    """Input for creating an organization."""
    pass


class OrganizationUpdate(BaseModel):
    """Input for updating an organization (all fields optional)."""
    name: str | None = None
    domain: str | None = None
    is_active: bool | None = None
    settings: dict | None = None


class OrganizationPublic(OrganizationBase):
    """Organization output for API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    created_by: str
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_dt(self, dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None


# =============================================================================
# User Schemas
# =============================================================================


class UserBase(BaseModel):
    """Shared user fields."""
    email: EmailStr = Field(max_length=320)
    name: str | None = Field(default=None, max_length=255)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    is_verified: bool = Field(default=False)
    is_registered: bool = Field(default=True)
    mfa_enabled: bool = Field(default=False)
    user_type: UserType = Field(default=UserType.ORG)


class UserCreate(BaseModel):
    """Input for creating a user."""
    email: EmailStr
    name: str | None = None
    password: str | None = None  # Plain text, will be hashed
    is_active: bool = True
    is_superuser: bool = False
    user_type: UserType = UserType.ORG
    organization_id: UUID | None = None


class UserUpdate(BaseModel):
    """Input for updating a user."""
    email: EmailStr | None = None
    name: str | None = None
    password: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None
    is_verified: bool | None = None
    mfa_enabled: bool | None = None
    organization_id: UUID | None = None


class UserPublic(UserBase):
    """User output for API responses (excludes sensitive fields)."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID | None
    last_login: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at", "last_login")
    def serialize_dt(self, dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None


# =============================================================================
# Role Schemas
# =============================================================================


class RoleBase(BaseModel):
    """Shared role fields."""
    name: str = Field(max_length=100)
    description: str | None = Field(default=None)
    is_active: bool = Field(default=True)


class RoleCreate(RoleBase):
    """Input for creating a role."""
    organization_id: UUID | None = None


class RoleUpdate(BaseModel):
    """Input for updating a role."""
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class RolePublic(RoleBase):
    """Role output for API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID | None
    created_by: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_dt(self, dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None


# =============================================================================
# Form Schemas
# =============================================================================


# FormSchema imported from shared.models above

class FormCreate(BaseModel):
    """Input for creating a form."""
    name: str
    description: str | None = None
    workflow_id: str | None = None
    default_launch_params: dict | None = None
    allowed_query_params: list[str] | None = None
    form_schema: dict | FormSchema
    access_level: FormAccessLevel | None = FormAccessLevel.ROLE_BASED

    @field_validator("form_schema", mode="before")
    @classmethod
    def validate_form_schema(cls, v):
        """Validate and convert dict to FormSchema if needed."""
        if v is None:
            raise ValueError("form_schema is required")
        if isinstance(v, dict):
            # Validate the dict conforms to FormSchema structure
            return FormSchema.model_validate(v)
        return v


class FormUpdate(BaseModel):
    """Input for updating a form."""
    name: str | None = None
    description: str | None = None
    workflow_id: str | None = None
    default_launch_params: dict | None = None
    allowed_query_params: list[str] | None = None
    form_schema: dict | FormSchema | None = None
    is_active: bool | None = None
    access_level: FormAccessLevel | None = None

    @field_validator("form_schema", mode="before")
    @classmethod
    def validate_form_schema(cls, v):
        """Validate and convert dict to FormSchema if needed."""
        if v is None:
            return None
        if isinstance(v, dict):
            # Validate the dict conforms to FormSchema structure
            return FormSchema.model_validate(v)
        return v


class FormPublic(BaseModel):
    """Form output for API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    workflow_id: str | None = None
    default_launch_params: dict | None = None
    allowed_query_params: list[str] | None = None
    form_schema: dict | FormSchema | None = None
    access_level: FormAccessLevel | None = None
    organization_id: UUID | None = None
    is_active: bool
    file_path: str | None = Field(None, description="Workspace-relative file path (e.g., 'forms/my-form-abc123.form.json')")
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def compute_form_schema(cls, data):
        """Compute form_schema from fields relationship if available."""
        if isinstance(data, dict):
            return data  # Already a dict, use as-is

        # It's an ORM object
        if hasattr(data, 'fields') and data.fields:
            # Build form_schema from fields relationship
            fields_data = []
            for field in sorted(data.fields, key=lambda f: f.position):
                field_dict = {
                    "name": field.name,
                    "type": field.type,
                    "required": field.required,
                }
                # Add optional fields
                if field.label:
                    field_dict["label"] = field.label
                if field.placeholder:
                    field_dict["placeholder"] = field.placeholder
                if field.help_text:
                    field_dict["help_text"] = field.help_text
                if field.default_value is not None:
                    field_dict["default_value"] = field.default_value
                if field.options:
                    field_dict["options"] = field.options
                if field.data_provider:
                    field_dict["data_provider"] = field.data_provider
                if field.data_provider_inputs:
                    field_dict["data_provider_inputs"] = field.data_provider_inputs
                if field.visibility_expression:
                    field_dict["visibility_expression"] = field.visibility_expression
                if field.validation:
                    field_dict["validation"] = field.validation
                if field.allowed_types:
                    field_dict["allowed_types"] = field.allowed_types
                if field.multiple is not None:
                    field_dict["multiple"] = field.multiple
                if field.max_size_mb:
                    field_dict["max_size_mb"] = field.max_size_mb
                if field.content:
                    field_dict["content"] = field.content

                fields_data.append(field_dict)

            # Create a new dict with form_schema computed
            data_dict = {
                "id": data.id,
                "name": data.name,
                "description": data.description,
                "workflow_id": data.workflow_id,
                "default_launch_params": data.default_launch_params,
                "allowed_query_params": data.allowed_query_params,
                "form_schema": {"fields": fields_data},
                "access_level": data.access_level,
                "organization_id": data.organization_id,
                "is_active": data.is_active,
                "file_path": data.file_path,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
            }
            return data_dict

        return data

    @field_validator("form_schema", mode="before")
    @classmethod
    def validate_form_schema(cls, v):
        """Validate and convert dict to FormSchema if needed."""
        if v is None:
            return None
        if isinstance(v, dict):
            # Validate the dict conforms to FormSchema structure
            return FormSchema.model_validate(v)
        return v

    @field_serializer("created_at", "updated_at")
    def serialize_dt(self, dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None


# =============================================================================
# Execution Schemas
# =============================================================================


class ExecutionBase(BaseModel):
    """Shared execution fields."""
    workflow_name: str = Field(max_length=255)
    workflow_version: str | None = Field(default=None, max_length=50)
    status: ExecutionStatus = Field(default=ExecutionStatus.PENDING)
    parameters: dict = Field(default_factory=dict)
    result: dict | None = Field(default=None)
    result_type: str | None = Field(default=None, max_length=50)
    variables: dict | None = Field(default=None)
    error_message: str | None = Field(default=None)


class ExecutionCreate(BaseModel):
    """Input for creating an execution."""
    workflow_name: str
    workflow_version: str | None = None
    parameters: dict = Field(default_factory=dict)
    form_id: UUID | None = None


class ExecutionUpdate(BaseModel):
    """Input for updating an execution (typically status updates)."""
    status: ExecutionStatus | None = None
    result: dict | None = None
    result_type: str | None = None
    variables: dict | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None


class ExecutionPublic(ExecutionBase):
    """Execution output for API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    executed_by: UUID
    executed_by_name: str
    organization_id: UUID | None
    form_id: UUID | None
    created_at: datetime

    @field_serializer("created_at", "started_at", "completed_at")
    def serialize_dt(self, dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None


# =============================================================================
# Config Schemas
# =============================================================================


class ConfigBase(BaseModel):
    """Shared config fields."""
    key: str = Field(max_length=255)
    value: dict
    config_type: ConfigType = Field(default=ConfigType.STRING)
    description: str | None = Field(default=None)


class ConfigCreate(ConfigBase):
    """Input for creating a config."""
    organization_id: UUID | None = None


class ConfigUpdate(BaseModel):
    """Input for updating a config."""
    value: dict | None = None
    config_type: ConfigType | None = None
    description: str | None = None


class ConfigPublic(ConfigBase):
    """Config output for API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID | None
    created_at: datetime
    updated_at: datetime
    updated_by: str

    @field_serializer("created_at", "updated_at")
    def serialize_dt(self, dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None


# =============================================================================
# Secret Schemas
# =============================================================================


class SecretBase(BaseModel):
    """Shared secret fields (note: encrypted_value is NOT exposed)."""
    name: str = Field(max_length=255)


class SecretCreate(SecretBase):
    """Input for creating a secret."""
    value: str  # Plain text value, will be encrypted
    organization_id: UUID | None = None


class SecretUpdate(BaseModel):
    """Input for updating a secret."""
    value: str | None = None  # Plain text value


class SecretPublic(SecretBase):
    """Secret output for API responses (value NOT included)."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_dt(self, dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None


# =============================================================================
# OAuth Schemas (for integrations)
# =============================================================================


class OAuthProviderBase(BaseModel):
    """Shared OAuth provider fields."""
    provider_name: str = Field(max_length=100)
    client_id: str = Field(max_length=255)
    scopes: list = Field(default_factory=list)
    provider_metadata: dict = Field(default_factory=dict)


class OAuthProviderCreate(OAuthProviderBase):
    """Input for creating an OAuth provider."""
    client_secret: str  # Plain text, will be encrypted
    organization_id: UUID | None = None


class OAuthProviderUpdate(BaseModel):
    """Input for updating an OAuth provider."""
    client_id: str | None = None
    client_secret: str | None = None
    scopes: list | None = None
    provider_metadata: dict | None = None


class OAuthProviderPublic(OAuthProviderBase):
    """OAuth provider output (secret NOT included)."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_dt(self, dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None


# =============================================================================
# Response/Request Schemas (for endpoints with computed/aggregated data)
# =============================================================================


class UserRolesResponse(BaseModel):
    """Response for user's assigned role IDs."""
    role_ids: list[str] = Field(alias="roleIds")

    model_config = ConfigDict(populate_by_name=True)


class UserFormsResponse(BaseModel):
    """Response for user's accessible forms."""
    user_type: UserType = Field(alias="userType")
    has_access_to_all_forms: bool = Field(alias="hasAccessToAllForms")
    form_ids: list[str] = Field(alias="formIds")

    model_config = ConfigDict(populate_by_name=True)


class RoleUsersResponse(BaseModel):
    """Response for users assigned to a role."""
    user_ids: list[str] = Field(alias="userIds")

    model_config = ConfigDict(populate_by_name=True)


class RoleFormsResponse(BaseModel):
    """Response for forms assigned to a role."""
    form_ids: list[str] = Field(alias="formIds")

    model_config = ConfigDict(populate_by_name=True)


class AssignUsersToRoleRequest(BaseModel):
    """Request to assign users to a role."""
    user_ids: list[str] = Field(alias="userIds")

    model_config = ConfigDict(populate_by_name=True)


class AssignFormsToRoleRequest(BaseModel):
    """Request to assign forms to a role."""
    form_ids: list[str] = Field(alias="formIds")

    model_config = ConfigDict(populate_by_name=True)
