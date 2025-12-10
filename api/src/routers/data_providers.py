"""
Data Providers Router

Returns metadata for all registered data providers.

Note: Data providers are discovered by the Discovery container and synced to
the database. This router queries the database for fast lookups.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

# Import existing Pydantic models for API compatibility
from src.models import DataProviderMetadata
from src.models import DataProvider as DataProviderORM

from src.core.auth import CurrentActiveUser
from src.core.database import DbSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data-providers", tags=["Data Providers"])


def _convert_provider_orm_to_schema(provider: DataProviderORM) -> DataProviderMetadata:
    """Convert ORM model to Pydantic schema for API response."""
    return DataProviderMetadata(
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
    user: CurrentActiveUser,
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
