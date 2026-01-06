"""
Tables Router

Manage tables and documents for app builder data storage.
Uses OrgScopedRepository for standardized org scoping.

Tables follow the same scoping pattern as configs:
- organization_id = NULL: Global table (platform-wide)
- organization_id = UUID: Organization-scoped table
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import Context, CurrentSuperuser
from src.core.org_filter import OrgFilterType, resolve_org_filter, resolve_target_org
from src.models.contracts.tables import (
    DocumentCountResponse,
    DocumentCreate,
    DocumentListResponse,
    DocumentPublic,
    DocumentQuery,
    DocumentUpdate,
    TableCreate,
    TableListResponse,
    TablePublic,
    TableUpdate,
)
from src.models.orm.tables import Document, Table
from src.repositories.org_scoped import OrgScopedRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tables", tags=["Tables"])


# =============================================================================
# Repository
# =============================================================================


class TableRepository(OrgScopedRepository[Table]):
    """Repository for table operations."""

    model = Table

    async def list_tables(
        self,
        filter_type: OrgFilterType = OrgFilterType.ORG_PLUS_GLOBAL,
    ) -> list[Table]:
        """List tables with specified filter type."""
        query = select(self.model)
        query = self.apply_filter(query, filter_type, self.org_id)
        query = query.order_by(self.model.name)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> Table | None:
        """Get table by name with cascade scoping."""
        query = select(self.model).where(self.model.name == name)
        query = self.filter_cascade(query)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_name_strict(self, name: str) -> Table | None:
        """Get table by name strictly in current org scope (no fallback)."""
        query = select(self.model).where(
            self.model.name == name,
            self.model.organization_id == self.org_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_table(
        self,
        data: TableCreate,
        created_by: str,
    ) -> Table:
        """Create a new table."""
        # Check if table already exists in this scope
        existing = await self.get_by_name_strict(data.name)
        if existing:
            raise ValueError(f"Table '{data.name}' already exists")

        table = Table(
            name=data.name,
            description=data.description,
            schema=data.schema,
            organization_id=self.org_id,
            created_by=created_by,
        )
        self.session.add(table)
        await self.session.flush()
        await self.session.refresh(table)

        logger.info(f"Created table '{data.name}' in org {self.org_id}")
        return table

    async def update_table(
        self,
        name: str,
        data: TableUpdate,
    ) -> Table | None:
        """Update a table."""
        table = await self.get_by_name_strict(name)
        if not table:
            return None

        if data.description is not None:
            table.description = data.description
        if data.schema is not None:
            table.schema = data.schema

        await self.session.flush()
        await self.session.refresh(table)

        logger.info(f"Updated table '{name}'")
        return table

    async def delete_table(self, name: str) -> bool:
        """Delete a table and all its documents (cascade)."""
        table = await self.get_by_name_strict(name)
        if not table:
            return False

        await self.session.delete(table)
        await self.session.flush()

        logger.info(f"Deleted table '{name}'")
        return True


def _build_document_filters(base_query: Any, where: dict[str, Any]) -> Any:
    """Build SQLAlchemy filters from where clause with JSON-native operators.

    Supports:
    - Simple equality: {"status": "active"}
    - Comparison operators: {"amount": {"gt": 100, "lte": 1000}}
    - Contains: {"name": {"contains": "acme"}} (case-insensitive substring)
    - Starts/ends with: {"name": {"starts_with": "a"}}
    - IN lists: {"category": {"in": ["a", "b"]}}
    - NULL checks: {"deleted_at": {"is_null": true}}
    - Has key: {"field": {"has_key": true}}
    """
    for field, value in where.items():
        json_field = Document.data[field]

        if isinstance(value, dict):
            # Operator-based filter
            for op, op_value in value.items():
                if op == "eq":
                    base_query = base_query.where(json_field.astext == str(op_value))
                elif op == "ne":
                    base_query = base_query.where(json_field.astext != str(op_value))
                elif op == "contains":
                    # Case-insensitive substring search
                    base_query = base_query.where(json_field.astext.ilike(f"%{op_value}%"))
                elif op == "starts_with":
                    base_query = base_query.where(json_field.astext.ilike(f"{op_value}%"))
                elif op == "ends_with":
                    base_query = base_query.where(json_field.astext.ilike(f"%{op_value}"))
                elif op == "gt":
                    base_query = base_query.where(
                        cast(json_field.astext, String) > str(op_value)
                    )
                elif op == "gte":
                    base_query = base_query.where(
                        cast(json_field.astext, String) >= str(op_value)
                    )
                elif op == "lt":
                    base_query = base_query.where(
                        cast(json_field.astext, String) < str(op_value)
                    )
                elif op == "lte":
                    base_query = base_query.where(
                        cast(json_field.astext, String) <= str(op_value)
                    )
                elif op in ("in", "in_"):
                    if isinstance(op_value, list):
                        base_query = base_query.where(
                            json_field.astext.in_([str(v) for v in op_value])
                        )
                elif op == "is_null":
                    if op_value:
                        base_query = base_query.where(json_field.is_(None))
                    else:
                        base_query = base_query.where(json_field.isnot(None))
                elif op == "has_key":
                    if op_value:
                        base_query = base_query.where(Document.data.has_key(field))
                    else:
                        base_query = base_query.where(~Document.data.has_key(field))
        else:
            # Simple equality
            base_query = base_query.where(json_field.astext == str(value))

    return base_query


class DocumentRepository:
    """Repository for document operations within a table."""

    def __init__(self, session: AsyncSession, table: Table):
        self.session = session
        self.table = table

    async def insert(self, data: dict[str, Any], created_by: str | None) -> Document:
        """Insert a new document."""
        doc = Document(
            table_id=self.table.id,
            data=data,
            created_by=created_by,
        )
        self.session.add(doc)
        await self.session.flush()
        await self.session.refresh(doc)
        return doc

    async def get(self, doc_id: str) -> Document | None:
        """Get document by ID."""
        query = select(Document).where(
            Document.id == doc_id,
            Document.table_id == self.table.id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update(
        self,
        doc_id: str,
        data: dict[str, Any],
        updated_by: str | None,
    ) -> Document | None:
        """Update a document (partial update, merges with existing)."""
        doc = await self.get(doc_id)
        if not doc:
            return None

        # Merge new data with existing
        merged_data = {**doc.data, **data}
        doc.data = merged_data
        doc.updated_by = updated_by

        await self.session.flush()
        await self.session.refresh(doc)
        return doc

    async def delete(self, doc_id: str) -> bool:
        """Delete a document."""
        doc = await self.get(doc_id)
        if not doc:
            return False

        await self.session.delete(doc)
        await self.session.flush()
        return True

    async def query(self, query_params: DocumentQuery) -> tuple[list[Document], int]:
        """Query documents with filtering and pagination."""
        base_query = select(Document).where(Document.table_id == self.table.id)

        # Apply where filters using JSON-native operators
        if query_params.where:
            base_query = _build_document_filters(base_query, query_params.where)

        # Get total count before pagination
        count_query = select(func.count()).select_from(base_query.subquery())
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0

        # Apply ordering
        if query_params.order_by:
            # Order by JSONB field
            order_expr = Document.data[query_params.order_by].astext
            if query_params.order_dir == "desc":
                order_expr = order_expr.desc()
            base_query = base_query.order_by(order_expr)
        else:
            # Default ordering by created_at
            if query_params.order_dir == "desc":
                base_query = base_query.order_by(Document.created_at.desc())
            else:
                base_query = base_query.order_by(Document.created_at.asc())

        # Apply pagination
        base_query = base_query.offset(query_params.offset).limit(query_params.limit)

        result = await self.session.execute(base_query)
        documents = list(result.scalars().all())

        return documents, total

    async def count(self, where: dict[str, Any] | None = None) -> int:
        """Count documents matching filter."""
        base_query = select(Document).where(Document.table_id == self.table.id)

        if where:
            base_query = _build_document_filters(base_query, where)

        count_query = select(func.count()).select_from(base_query.subquery())
        result = await self.session.execute(count_query)
        return result.scalar() or 0


# =============================================================================
# Helper functions
# =============================================================================


def _resolve_target_org_safe(ctx: Context, scope: str | None) -> UUID | None:
    """Resolve the target organization ID from scope parameter (with auth check)."""
    try:
        return resolve_target_org(ctx.user, scope, ctx.org_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


async def get_table_or_404(
    ctx: Context,
    name: str,
    scope: str | None = None,
) -> Table:
    """Get table by name or raise 404."""
    target_org_id = _resolve_target_org_safe(ctx, scope)
    repo = TableRepository(ctx.db, target_org_id)
    table = await repo.get_by_name(name)

    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{name}' not found",
        )

    return table


async def get_or_create_table(
    ctx: Context,
    name: str,
    scope: str | None = None,
    created_by: str | None = None,
) -> Table:
    """Get table by name, auto-creating if it doesn't exist.

    This is used by insert/upsert/query operations to enable
    schema-less table usage without explicit table creation.
    """
    target_org_id = _resolve_target_org_safe(ctx, scope)
    repo = TableRepository(ctx.db, target_org_id)
    table = await repo.get_by_name(name)

    if not table:
        # Auto-create table with minimal defaults
        from src.models.contracts.tables import TableCreate

        table_data = TableCreate(name=name)
        table = await repo.create_table(table_data, created_by=created_by or "system")
        logger.info(f"Auto-created table '{name}' in org {target_org_id}")

    return table


# =============================================================================
# Table Endpoints
# =============================================================================


@router.post(
    "",
    response_model=TablePublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a table",
)
async def create_table(
    data: TableCreate,
    ctx: Context,
    user: CurrentSuperuser,
    scope: str | None = Query(
        default=None,
        description="Target scope: 'global' or org UUID. Defaults to current org.",
    ),
) -> TablePublic:
    """Create a new table for storing documents (platform admin only)."""
    target_org_id = _resolve_target_org_safe(ctx, scope)
    repo = TableRepository(ctx.db, target_org_id)

    try:
        table = await repo.create_table(data, created_by=user.email)
        return TablePublic.model_validate(table)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.get(
    "",
    response_model=TableListResponse,
    summary="List tables",
)
async def list_tables(
    ctx: Context,
    user: CurrentSuperuser,
    scope: str | None = Query(
        default=None,
        description="Filter scope: 'global' for global only, org UUID for specific org.",
    ),
) -> TableListResponse:
    """List all tables in the current scope (platform admin only)."""
    try:
        filter_type, filter_org = resolve_org_filter(ctx.user, scope)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    repo = TableRepository(ctx.db, filter_org)
    tables = await repo.list_tables(filter_type)

    return TableListResponse(
        tables=[TablePublic.model_validate(t) for t in tables],
        total=len(tables),
    )


@router.get(
    "/{name}",
    response_model=TablePublic,
    summary="Get table metadata",
)
async def get_table(
    name: str,
    ctx: Context,
    user: CurrentSuperuser,
    scope: str | None = Query(default=None),
) -> TablePublic:
    """Get table metadata by name (platform admin only)."""
    table = await get_table_or_404(ctx, name, scope)
    return TablePublic.model_validate(table)


@router.patch(
    "/{name}",
    response_model=TablePublic,
    summary="Update table",
)
async def update_table(
    name: str,
    data: TableUpdate,
    ctx: Context,
    user: CurrentSuperuser,
    scope: str | None = Query(default=None),
) -> TablePublic:
    """Update table metadata (platform admin only)."""
    target_org_id = _resolve_target_org_safe(ctx, scope)
    repo = TableRepository(ctx.db, target_org_id)
    table = await repo.update_table(name, data)

    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{name}' not found",
        )

    return TablePublic.model_validate(table)


@router.delete(
    "/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete table",
)
async def delete_table(
    name: str,
    ctx: Context,
    user: CurrentSuperuser,
    scope: str | None = Query(default=None),
) -> None:
    """Delete a table and all its documents (platform admin only)."""
    target_org_id = _resolve_target_org_safe(ctx, scope)
    repo = TableRepository(ctx.db, target_org_id)
    success = await repo.delete_table(name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{name}' not found",
        )


# =============================================================================
# Document Endpoints
# =============================================================================


@router.post(
    "/{name}/documents",
    response_model=DocumentPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Insert a document",
)
async def insert_document(
    name: str,
    data: DocumentCreate,
    ctx: Context,
    user: CurrentSuperuser,
    scope: str | None = Query(default=None),
) -> DocumentPublic:
    """Insert a new document into the table (platform admin only).

    Auto-creates the table if it doesn't exist.
    """
    table = await get_or_create_table(ctx, name, scope, created_by=user.email)
    repo = DocumentRepository(ctx.db, table)

    doc = await repo.insert(data.data, created_by=user.email)
    return DocumentPublic.model_validate(doc)


@router.get(
    "/{name}/documents/{doc_id}",
    response_model=DocumentPublic,
    summary="Get a document",
)
async def get_document(
    name: str,
    doc_id: str,
    ctx: Context,
    user: CurrentSuperuser,
    scope: str | None = Query(default=None),
) -> DocumentPublic:
    """Get a document by ID (platform admin only)."""
    table = await get_table_or_404(ctx, name, scope)
    repo = DocumentRepository(ctx.db, table)

    doc = await repo.get(doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return DocumentPublic.model_validate(doc)


@router.patch(
    "/{name}/documents/{doc_id}",
    response_model=DocumentPublic,
    summary="Update a document",
)
async def update_document(
    name: str,
    doc_id: str,
    data: DocumentUpdate,
    ctx: Context,
    user: CurrentSuperuser,
    scope: str | None = Query(default=None),
) -> DocumentPublic:
    """Update a document (platform admin only, partial update, merges with existing)."""
    table = await get_table_or_404(ctx, name, scope)
    repo = DocumentRepository(ctx.db, table)

    doc = await repo.update(doc_id, data.data, updated_by=user.email)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return DocumentPublic.model_validate(doc)


@router.delete(
    "/{name}/documents/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
)
async def delete_document(
    name: str,
    doc_id: str,
    ctx: Context,
    user: CurrentSuperuser,
    scope: str | None = Query(default=None),
) -> None:
    """Delete a document (platform admin only)."""
    table = await get_table_or_404(ctx, name, scope)
    repo = DocumentRepository(ctx.db, table)

    success = await repo.delete(doc_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )


@router.post(
    "/{name}/documents/query",
    response_model=DocumentListResponse,
    summary="Query documents",
)
async def query_documents(
    name: str,
    query_params: DocumentQuery,
    ctx: Context,
    user: CurrentSuperuser,
    scope: str | None = Query(default=None),
) -> DocumentListResponse:
    """Query documents with filtering and pagination (platform admin only).

    Auto-creates the table if it doesn't exist (returns empty results).
    """
    table = await get_or_create_table(ctx, name, scope, created_by=user.email)
    repo = DocumentRepository(ctx.db, table)

    documents, total = await repo.query(query_params)

    return DocumentListResponse(
        documents=[DocumentPublic.model_validate(d) for d in documents],
        total=total,
        limit=query_params.limit,
        offset=query_params.offset,
    )


@router.get(
    "/{name}/documents/count",
    response_model=DocumentCountResponse,
    summary="Count documents",
)
async def count_documents(
    name: str,
    ctx: Context,
    user: CurrentSuperuser,
    scope: str | None = Query(default=None),
) -> DocumentCountResponse:
    """Count documents in a table (platform admin only).

    Auto-creates the table if it doesn't exist (returns 0).
    """
    table = await get_or_create_table(ctx, name, scope, created_by=user.email)
    repo = DocumentRepository(ctx.db, table)

    count = await repo.count()
    return DocumentCountResponse(count=count)
