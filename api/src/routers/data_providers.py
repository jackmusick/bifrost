"""
Data Providers Router

Returns metadata for all registered data providers and allows invocation.

Note: Data providers are discovered by the Discovery container and synced to
the database. This router queries the database for fast lookups.
"""

import logging
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import exists, select

# Import existing Pydantic models for API compatibility
from src.models import DataProviderMetadata
from src.models import DataProvider as DataProviderORM
from src.models.orm.forms import FormField as FormFieldORM, FormRole as FormRoleORM
from src.models.orm.users import UserRole as UserRoleORM
from src.models.orm.integrations import Integration as IntegrationORM

from src.core.auth import Context, CurrentActiveUser, CurrentSuperuser
from src.core.database import DbSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data-providers", tags=["Data Providers"])


# ==================== REQUEST/RESPONSE MODELS ====================


class DataProviderInvokeRequest(BaseModel):
    """Request to invoke a data provider."""
    inputs: dict[str, Any] = Field(default_factory=dict, description="Input parameters for the data provider")


class DataProviderOption(BaseModel):
    """A single option from a data provider."""
    value: str = Field(..., description="Option value")
    label: str = Field(..., description="Option display label")
    description: str | None = Field(default=None, description="Optional description")


class DataProviderInvokeResponse(BaseModel):
    """Response from invoking a data provider."""
    options: list[DataProviderOption] = Field(default_factory=list, description="List of options from the provider")


def _convert_provider_orm_to_schema(provider: DataProviderORM) -> DataProviderMetadata:
    """Convert ORM model to Pydantic schema for API response."""
    return DataProviderMetadata(
        id=str(provider.id),
        name=provider.name,
        description=provider.description or "",
        category="General",
        cache_ttl_seconds=300,
        parameters=[],
        source_file_path=provider.file_path,
        relative_file_path=None,
    )


@router.get(
    "",
    response_model=list[DataProviderMetadata],
    summary="List all data providers",
    description="Returns metadata for all registered data providers in the system",
)
async def list_data_providers(
    user: CurrentSuperuser,
    db: DbSession,
) -> list[DataProviderMetadata]:
    """List all registered data providers from the database.

    Data providers are discovered by the Discovery container and synced to the
    database. This endpoint queries the database for fast lookups.
    """
    try:
        # Query active data providers from database
        query = select(DataProviderORM).where(DataProviderORM.is_active.is_(True))
        result = await db.execute(query)
        providers = result.scalars().all()

        # Convert ORM models to Pydantic schemas
        provider_list = []
        for dp in providers:
            try:
                provider_list.append(_convert_provider_orm_to_schema(dp))
            except Exception as e:
                logger.error(f"Failed to convert data provider '{dp.name}': {e}")

        logger.info(f"Returning {len(provider_list)} data providers")
        return provider_list

    except Exception as e:
        logger.error(f"Error retrieving data providers: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve data providers",
        )


async def _check_data_provider_access(
    db: DbSession,
    provider_id: UUID,
    user_id: UUID,
    is_superuser: bool,
) -> bool:
    """Check if user has access to invoke a data provider.

    User can invoke a data provider if:
    1. User is a platform admin (superuser)
    2. User has access to a form that uses this data provider
    3. User has access to an integration that uses this data provider

    Args:
        db: Database session
        provider_id: Data provider ID
        user_id: User ID
        is_superuser: Whether user is a platform admin

    Returns:
        True if user has access, False otherwise
    """
    # Platform admins can access all data providers
    if is_superuser:
        return True

    # Check if user has access via form field
    # User -> UserRole -> FormRole -> Form -> FormField.data_provider_id
    form_access_query = (
        select(exists())
        .where(
            UserRoleORM.user_id == user_id,
        )
        .where(
            exists(
                select(FormRoleORM.form_id)
                .where(FormRoleORM.role_id == UserRoleORM.role_id)
                .where(
                    exists(
                        select(FormFieldORM.id)
                        .where(FormFieldORM.form_id == FormRoleORM.form_id)
                        .where(FormFieldORM.data_provider_id == provider_id)
                    )
                )
            )
        )
    )

    form_result = await db.execute(form_access_query)
    if form_result.scalar():
        return True

    # Check if user has access via integration
    # For now, allow access to integration entity providers for any authenticated user
    # Future: Could add more granular integration access control
    integration_query = select(exists()).where(
        IntegrationORM.list_entities_data_provider_id == provider_id,
        IntegrationORM.is_deleted.is_(False),
    )

    integration_result = await db.execute(integration_query)
    if integration_result.scalar():
        return True

    return False


@router.post(
    "/{provider_id}/invoke",
    response_model=DataProviderInvokeResponse,
    summary="Invoke a data provider",
    description="Execute a data provider and return its options. User must have access via form or integration.",
)
async def invoke_data_provider(
    provider_id: UUID,
    request: DataProviderInvokeRequest,
    db: DbSession,
    ctx: Context,
) -> DataProviderInvokeResponse:
    """Execute a data provider and return its options.

    Authorization: User must have access to a form using this provider,
    be a platform admin, or the provider is tied to an integration.
    """
    from src.sdk.context import ExecutionContext as SharedContext, Organization
    from src.services.execution.service import (
        run_data_provider,
        DataProviderNotFoundError,
        DataProviderLoadError,
    )

    # Look up provider by ID
    result = await db.execute(
        select(DataProviderORM).where(
            DataProviderORM.id == provider_id,
            DataProviderORM.is_active.is_(True),
        )
    )
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data provider not found",
        )

    # Check authorization
    has_access = await _check_data_provider_access(
        db, provider_id, ctx.user.user_id, ctx.user.is_superuser
    )

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this data provider",
        )

    # Create organization object if org_id is set
    org = None
    if ctx.org_id:
        org = Organization(id=str(ctx.org_id), name="", is_active=True)

    # Create shared context for execution
    shared_ctx = SharedContext(
        user_id=str(ctx.user.user_id),
        name=ctx.user.name,
        email=ctx.user.email,
        scope=str(ctx.org_id) if ctx.org_id else "GLOBAL",
        organization=org,
        is_platform_admin=ctx.user.is_superuser,
        is_function_key=False,
        execution_id=str(uuid4()),
    )

    try:
        # Execute data provider by name (execution service uses name)
        options = await run_data_provider(
            context=shared_ctx,
            provider_name=provider.name,
            params=request.inputs,
        )

        # Convert to response format
        response_options = []
        for opt in options:
            if isinstance(opt, dict):
                response_options.append(DataProviderOption(
                    value=str(opt.get("value", opt.get("id", ""))),
                    label=str(opt.get("label", opt.get("name", opt.get("value", "")))),
                    description=opt.get("description"),
                ))
            else:
                # Handle simple string options
                response_options.append(DataProviderOption(
                    value=str(opt),
                    label=str(opt),
                ))

        logger.info(f"Data provider {provider.name} invoked by {ctx.user.email}, returned {len(response_options)} options")

        return DataProviderInvokeResponse(options=response_options)

    except DataProviderNotFoundError:
        logger.error(f"Data provider {provider.name} not found during execution")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Data provider '{provider.name}' not found",
        )
    except DataProviderLoadError as e:
        logger.error(f"Failed to load data provider {provider.name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load data provider: {str(e)}",
        )
    except RuntimeError as e:
        logger.error(f"Data provider {provider.name} execution failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Data provider execution failed: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Unexpected error invoking data provider {provider.name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute data provider",
        )
