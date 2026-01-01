"""
Unit tests for Bifrost Tables SDK module.

Tests SDK module structure and API method signatures.
Integration tests for actual API calls are in tests/integration/platform/.
"""

import pytest


class TestTablesSDKImports:
    """Test that tables SDK can be imported correctly."""

    def test_import_bifrost_tables(self):
        """Test importing tables module."""
        from bifrost import tables

        # Verify module has expected methods
        assert hasattr(tables, 'create')
        assert hasattr(tables, 'list')
        assert hasattr(tables, 'delete')
        assert hasattr(tables, 'insert')
        assert hasattr(tables, 'get')
        assert hasattr(tables, 'update')
        assert hasattr(tables, 'delete_document')
        assert hasattr(tables, 'query')
        assert hasattr(tables, 'count')

    def test_import_table_models(self):
        """Test importing table models."""
        from bifrost import TableInfo, DocumentData, DocumentList

        assert TableInfo is not None
        assert DocumentData is not None
        assert DocumentList is not None

    def test_table_info_model_fields(self):
        """Test TableInfo model has expected fields."""
        from bifrost import TableInfo

        # Create instance to verify fields work
        table = TableInfo(
            id="test-id",
            name="customers",
            description="Customer data",
            table_schema={"type": "object"},
            organization_id="org-123",
            created_by="test@example.com",
        )

        assert table.id == "test-id"
        assert table.name == "customers"
        assert table.description == "Customer data"
        assert table.table_schema == {"type": "object"}
        assert table.organization_id == "org-123"

    def test_document_data_model_fields(self):
        """Test DocumentData model has expected fields."""
        from bifrost import DocumentData

        doc = DocumentData(
            id="doc-id",
            table_id="table-id",
            data={"name": "Acme", "status": "active"},
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

        assert doc.id == "doc-id"
        assert doc.table_id == "table-id"
        assert doc.data["name"] == "Acme"
        assert doc.data["status"] == "active"

    def test_document_list_model_fields(self):
        """Test DocumentList model has expected fields."""
        from bifrost import DocumentData, DocumentList

        doc = DocumentData(
            id="doc-id",
            table_id="table-id",
            data={"name": "Acme"},
        )

        doc_list = DocumentList(
            documents=[doc],
            total=100,
            limit=10,
            offset=0,
        )

        assert len(doc_list.documents) == 1
        assert doc_list.total == 100
        assert doc_list.limit == 10
        assert doc_list.offset == 0


class TestTablesSDKWithoutContext:
    """Test SDK behavior without execution context."""

    @pytest.mark.asyncio
    async def test_tables_create_without_context_raises_error(self):
        """Test that tables.create raises error when not authenticated."""
        from bifrost import tables
        from bifrost.client import _clear_client
        from bifrost._context import clear_execution_context

        # Ensure no context is set and no client injected
        clear_execution_context()
        _clear_client()

        # Attempting to use SDK should raise RuntimeError about not being logged in
        with pytest.raises(RuntimeError, match="Not logged in"):
            await tables.create("test_table")

    @pytest.mark.asyncio
    async def test_tables_list_without_context_raises_error(self):
        """Test that tables.list raises error when not authenticated."""
        from bifrost import tables
        from bifrost.client import _clear_client
        from bifrost._context import clear_execution_context

        clear_execution_context()
        _clear_client()

        with pytest.raises(RuntimeError, match="Not logged in"):
            await tables.list()

    @pytest.mark.asyncio
    async def test_tables_insert_without_context_raises_error(self):
        """Test that tables.insert raises error when not authenticated."""
        from bifrost import tables
        from bifrost.client import _clear_client
        from bifrost._context import clear_execution_context

        clear_execution_context()
        _clear_client()

        with pytest.raises(RuntimeError, match="Not logged in"):
            await tables.insert("customers", {"name": "Test"})

    @pytest.mark.asyncio
    async def test_tables_query_without_context_raises_error(self):
        """Test that tables.query raises error when not authenticated."""
        from bifrost import tables
        from bifrost.client import _clear_client
        from bifrost._context import clear_execution_context

        clear_execution_context()
        _clear_client()

        with pytest.raises(RuntimeError, match="Not logged in"):
            await tables.query("customers")
