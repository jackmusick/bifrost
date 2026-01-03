"""
Tables SDK for Bifrost - API-only implementation.

Provides Python API for table and document management (CRUD operations).
All operations go through HTTP API endpoints.
All methods are async and must be awaited.
"""

from __future__ import annotations

from typing import Any

from .client import get_client
from .models import TableInfo, DocumentData, DocumentList


class tables:
    """
    Table and document management operations.

    Allows workflows to create tables and store/query documents.
    All operations are performed via HTTP API endpoints.

    All methods are async - await is required.

    Example:
        >>> from bifrost import tables
        >>> # Create a table
        >>> table = await tables.create("customers", table_schema={"type": "object"})
        >>> # Insert a document
        >>> doc = await tables.insert("customers", {"name": "Acme", "email": "info@acme.com"})
        >>> # Query with comparison operators
        >>> results = await tables.query(
        ...     "customers",
        ...     where={
        ...         "status": "active",
        ...         "revenue": {"gte": 10000},
        ...         "name": {"ilike": "%acme%"}
        ...     }
        ... )
        >>> for doc in results.documents:
        ...     print(doc.data)
    """

    # =========================================================================
    # Table Operations
    # =========================================================================

    @staticmethod
    async def create(
        name: str,
        description: str | None = None,
        table_schema: dict[str, Any] | None = None,
        scope: str | None = None,
        app: str | None = None,
    ) -> TableInfo:
        """
        Create a new table.

        Args:
            name: Table name (unique within scope)
            description: Optional table description
            table_schema: Optional JSON Schema for document validation
            scope: Organization scope - can be:
                - None: Use execution context default org
                - org UUID string: Target specific organization
                - "global": Create a global table
            app: Application UUID to scope table to a specific app

        Returns:
            TableInfo: Created table metadata

        Raises:
            RuntimeError: If not authenticated
            HTTPError: If table already exists (409) or other API error

        Example:
            >>> from bifrost import tables
            >>> table = await tables.create("customers")
            >>> app_table = await tables.create("app_data", app="app-uuid")
        """
        client = get_client()
        response = await client.post(
            "/api/cli/tables/create",
            json={
                "name": name,
                "description": description,
                "table_schema": table_schema,
                "scope": scope,
                "app": app,
            }
        )
        response.raise_for_status()
        return TableInfo.model_validate(response.json())

    @staticmethod
    async def list(
        scope: str | None = None,
        app: str | None = None,
    ) -> list[TableInfo]:
        """
        List all tables in the current scope.

        Args:
            scope: Organization scope - can be:
                - None: Use execution context default org (includes global)
                - org UUID string: Target specific organization
                - "global": List only global tables
            app: Filter by application UUID

        Returns:
            list[TableInfo]: List of table metadata

        Raises:
            RuntimeError: If not authenticated

        Example:
            >>> from bifrost import tables
            >>> all_tables = await tables.list()
            >>> app_tables = await tables.list(app="app-uuid")
        """
        client = get_client()
        response = await client.post(
            "/api/cli/tables/list",
            json={"scope": scope, "app": app}
        )
        response.raise_for_status()
        data = response.json()
        return [TableInfo.model_validate(t) for t in data.get("tables", [])]

    @staticmethod
    async def delete(
        name: str,
        scope: str | None = None,
        app: str | None = None,
    ) -> bool:
        """
        Delete a table and all its documents.

        Args:
            name: Table name
            scope: Organization scope
            app: Application UUID

        Returns:
            bool: True if deleted successfully

        Raises:
            RuntimeError: If not authenticated
            HTTPError: If table not found (404)

        Example:
            >>> from bifrost import tables
            >>> await tables.delete("old_customers")
        """
        client = get_client()
        response = await client.post(
            "/api/cli/tables/delete",
            json={"name": name, "scope": scope, "app": app}
        )
        response.raise_for_status()
        return response.json()

    # =========================================================================
    # Document Operations
    # =========================================================================

    @staticmethod
    async def insert(
        table: str,
        data: dict[str, Any],
        id: str | None = None,
        scope: str | None = None,
        app: str | None = None,
    ) -> DocumentData:
        """
        Insert a document into a table.

        Auto-creates the table if it doesn't exist.

        Args:
            table: Table name
            data: Document data (JSON-serializable dict)
            id: Document ID (user-provided key). If not provided, a UUID is auto-generated.
            scope: Organization scope
            app: Application UUID

        Returns:
            DocumentData: Created document with ID and timestamps

        Raises:
            RuntimeError: If not authenticated
            HTTPError: If document with id already exists (409 Conflict)

        Example:
            >>> from bifrost import tables
            >>> # Auto-generated ID
            >>> doc = await tables.insert("customers", {
            ...     "name": "Acme Corp",
            ...     "email": "info@acme.com",
            ... })
            >>> # User-provided ID
            >>> doc = await tables.insert("customers", id="acme-001", data={
            ...     "name": "Acme Corp",
            ...     "email": "info@acme.com",
            ... })
        """
        client = get_client()
        response = await client.post(
            "/api/cli/tables/documents/insert",
            json={
                "table": table,
                "id": id,
                "data": data,
                "scope": scope,
                "app": app,
            }
        )
        response.raise_for_status()
        return DocumentData.model_validate(response.json())

    @staticmethod
    async def upsert(
        table: str,
        id: str,
        data: dict[str, Any],
        scope: str | None = None,
        app: str | None = None,
    ) -> DocumentData:
        """
        Upsert (create or replace) a document.

        Auto-creates the table if it doesn't exist.
        If a document with the given id exists, it is replaced with the new data.
        If not, a new document is created.

        Args:
            table: Table name
            id: Document ID (required for upsert)
            data: Document data (JSON-serializable dict)
            scope: Organization scope
            app: Application UUID

        Returns:
            DocumentData: Created or updated document with ID and timestamps

        Raises:
            RuntimeError: If not authenticated

        Example:
            >>> from bifrost import tables
            >>> doc = await tables.upsert("employees", id="john@example.com", data={
            ...     "name": "John Doe",
            ...     "department": "Engineering",
            ... })
        """
        client = get_client()
        response = await client.post(
            "/api/cli/tables/documents/upsert",
            json={
                "table": table,
                "id": id,
                "data": data,
                "scope": scope,
                "app": app,
            }
        )
        response.raise_for_status()
        return DocumentData.model_validate(response.json())

    @staticmethod
    async def get(
        table: str,
        doc_id: str,
        scope: str | None = None,
        app: str | None = None,
    ) -> DocumentData | None:
        """
        Get a document by ID.

        Args:
            table: Table name
            doc_id: Document ID (user-provided or auto-generated)
            scope: Organization scope
            app: Application UUID

        Returns:
            DocumentData if found, None if not found

        Raises:
            RuntimeError: If not authenticated

        Example:
            >>> from bifrost import tables
            >>> doc = await tables.get("customers", "acme-001")
        """
        client = get_client()
        response = await client.post(
            "/api/cli/tables/documents/get",
            json={
                "table": table,
                "doc_id": doc_id,
                "scope": scope,
                "app": app,
            }
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        if data is None:
            return None
        return DocumentData.model_validate(data)

    @staticmethod
    async def update(
        table: str,
        doc_id: str,
        data: dict[str, Any],
        scope: str | None = None,
        app: str | None = None,
    ) -> DocumentData | None:
        """
        Update a document (partial update, merges with existing).

        Args:
            table: Table name
            doc_id: Document UUID
            data: Fields to update (merged with existing data)
            scope: Organization scope
            app: Application UUID

        Returns:
            DocumentData if updated, None if not found

        Raises:
            RuntimeError: If not authenticated

        Example:
            >>> from bifrost import tables
            >>> doc = await tables.update("customers", "uuid-here", {"status": "inactive"})
        """
        client = get_client()
        response = await client.post(
            "/api/cli/tables/documents/update",
            json={
                "table": table,
                "doc_id": doc_id,
                "data": data,
                "scope": scope,
                "app": app,
            }
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        result = response.json()
        if result is None:
            return None
        return DocumentData.model_validate(result)

    @staticmethod
    async def delete_document(
        table: str,
        doc_id: str,
        scope: str | None = None,
        app: str | None = None,
    ) -> bool:
        """
        Delete a document.

        Args:
            table: Table name
            doc_id: Document UUID
            scope: Organization scope
            app: Application UUID

        Returns:
            bool: True if deleted, False if not found

        Raises:
            RuntimeError: If not authenticated

        Example:
            >>> from bifrost import tables
            >>> deleted = await tables.delete_document("customers", "uuid-here")
        """
        client = get_client()
        response = await client.post(
            "/api/cli/tables/documents/delete",
            json={
                "table": table,
                "doc_id": doc_id,
                "scope": scope,
                "app": app,
            }
        )
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return response.json()

    @staticmethod
    async def query(
        table: str,
        where: dict[str, Any] | None = None,
        order_by: str | None = None,
        order_dir: str = "asc",
        limit: int = 100,
        offset: int = 0,
        scope: str | None = None,
        app: str | None = None,
    ) -> DocumentList:
        """
        Query documents with filtering and pagination.

        Supports advanced filter operators:
        - Simple equality: {"status": "active"}
        - Comparison: {"amount": {"gt": 100, "lte": 1000}}
        - LIKE patterns: {"name": {"like": "%acme%"}} or {"name": {"ilike": "%ACME%"}}
        - IN lists: {"category": {"in": ["a", "b"]}}
        - NULL checks: {"deleted_at": {"is_null": True}}

        Args:
            table: Table name
            where: Filter conditions with optional operators
            order_by: Field name to order by (JSONB field)
            order_dir: "asc" or "desc"
            limit: Maximum documents to return (default 100)
            offset: Number of documents to skip
            scope: Organization scope
            app: Application UUID

        Returns:
            DocumentList: Query results with documents, total count, and pagination info

        Raises:
            RuntimeError: If not authenticated
            HTTPError: If table not found (404)

        Example:
            >>> from bifrost import tables
            >>> # Simple equality filter
            >>> results = await tables.query("customers", where={"status": "active"})
            >>>
            >>> # Range query
            >>> results = await tables.query(
            ...     "orders",
            ...     where={"amount": {"gte": 100, "lt": 1000}}
            ... )
            >>>
            >>> # Case-insensitive search
            >>> results = await tables.query(
            ...     "customers",
            ...     where={"name": {"ilike": "%acme%"}}
            ... )
        """
        client = get_client()
        response = await client.post(
            "/api/cli/tables/documents/query",
            json={
                "table": table,
                "where": where,
                "order_by": order_by,
                "order_dir": order_dir,
                "limit": limit,
                "offset": offset,
                "scope": scope,
                "app": app,
            }
        )
        response.raise_for_status()
        return DocumentList.model_validate(response.json())

    @staticmethod
    async def count(
        table: str,
        where: dict[str, Any] | None = None,
        scope: str | None = None,
        app: str | None = None,
    ) -> int:
        """
        Count documents matching filter.

        Args:
            table: Table name
            where: Filter conditions with optional operators (same as query)
            scope: Organization scope
            app: Application UUID

        Returns:
            int: Number of matching documents

        Raises:
            RuntimeError: If not authenticated
            HTTPError: If table not found (404)

        Example:
            >>> from bifrost import tables
            >>> total = await tables.count("customers")
            >>> active = await tables.count("customers", where={"status": "active"})
            >>> high_value = await tables.count("customers", where={"revenue": {"gte": 10000}})
        """
        client = get_client()
        response = await client.post(
            "/api/cli/tables/documents/count",
            json={
                "table": table,
                "where": where,
                "scope": scope,
                "app": app,
            }
        )
        response.raise_for_status()
        return response.json()
