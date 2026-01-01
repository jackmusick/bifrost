"""
Integration tests for Tables API.

Tests table and document endpoints with real PostgreSQL database.
These tests require PostgreSQL to be running (via docker-compose.test.yml).
"""

import pytest
import pytest_asyncio
from uuid import uuid4

from sqlalchemy import delete, select

from src.core.database import get_db_context
from src.models.orm.tables import Table, Document
from src.routers.tables import TableRepository, DocumentRepository


@pytest.fixture
def test_org_id():
    """Generate unique org ID for test isolation."""
    return uuid4()


@pytest.fixture
def test_user_email():
    """Test user email."""
    return "test@example.com"


@pytest_asyncio.fixture
async def cleanup_tables(test_org_id):
    """Cleanup tables created during tests."""
    created_table_ids = []
    yield created_table_ids
    # Cleanup after test
    async with get_db_context() as db:
        for table_id in created_table_ids:
            stmt = delete(Table).where(Table.id == table_id)
            await db.execute(stmt)
        await db.commit()


class TestTableRepositoryIntegration:
    """Integration tests for TableRepository with real PostgreSQL."""

    @pytest.mark.asyncio
    async def test_create_and_get_table(self, test_org_id, test_user_email, cleanup_tables):
        """Test creating and retrieving a table."""
        async with get_db_context() as db:
            repo = TableRepository(db, test_org_id)

            # Create table
            from src.models.contracts.tables import TableCreate
            table_data = TableCreate(
                name=f"test_customers_{uuid4().hex[:8]}",
                description="Customer records",
                schema={"type": "object", "properties": {"name": {"type": "string"}}},
            )

            table = await repo.create_table(table_data, created_by=test_user_email)
            cleanup_tables.append(table.id)

            assert table.id is not None
            assert table.name == table_data.name
            assert table.description == "Customer records"
            assert table.organization_id == test_org_id

            # Retrieve table
            retrieved = await repo.get_by_name(table_data.name)
            assert retrieved is not None
            assert retrieved.id == table.id

    @pytest.mark.asyncio
    async def test_list_tables(self, test_org_id, test_user_email, cleanup_tables):
        """Test listing tables."""
        async with get_db_context() as db:
            repo = TableRepository(db, test_org_id)

            # Create multiple tables
            from src.models.contracts.tables import TableCreate
            for i in range(3):
                table_data = TableCreate(
                    name=f"test_table_{uuid4().hex[:8]}_{i}",
                    description=f"Test table {i}",
                )
                table = await repo.create_table(table_data, created_by=test_user_email)
                cleanup_tables.append(table.id)

            # List tables
            tables = await repo.list_tables()
            assert len(tables) >= 3

    @pytest.mark.asyncio
    async def test_update_table(self, test_org_id, test_user_email, cleanup_tables):
        """Test updating a table."""
        async with get_db_context() as db:
            repo = TableRepository(db, test_org_id)

            from src.models.contracts.tables import TableCreate, TableUpdate
            table_data = TableCreate(
                name=f"test_update_{uuid4().hex[:8]}",
                description="Original description",
            )
            table = await repo.create_table(table_data, created_by=test_user_email)
            cleanup_tables.append(table.id)

            # Update table
            update_data = TableUpdate(
                description="Updated description",
                schema={"type": "object"},
            )
            updated = await repo.update_table(table_data.name, update_data)

            assert updated is not None
            assert updated.description == "Updated description"
            assert updated.schema == {"type": "object"}

    @pytest.mark.asyncio
    async def test_delete_table(self, test_org_id, test_user_email):
        """Test deleting a table."""
        async with get_db_context() as db:
            repo = TableRepository(db, test_org_id)

            from src.models.contracts.tables import TableCreate
            table_data = TableCreate(
                name=f"test_delete_{uuid4().hex[:8]}",
            )
            await repo.create_table(table_data, created_by=test_user_email)

            # Delete table
            success = await repo.delete_table(table_data.name)
            assert success is True

            # Verify it's gone
            retrieved = await repo.get_by_name(table_data.name)
            assert retrieved is None

    @pytest.mark.asyncio
    async def test_duplicate_table_name_raises_error(self, test_org_id, test_user_email, cleanup_tables):
        """Test that creating a table with duplicate name raises error."""
        async with get_db_context() as db:
            repo = TableRepository(db, test_org_id)

            from src.models.contracts.tables import TableCreate
            table_name = f"test_duplicate_{uuid4().hex[:8]}"
            table_data = TableCreate(name=table_name)

            table = await repo.create_table(table_data, created_by=test_user_email)
            cleanup_tables.append(table.id)

            # Try to create with same name
            with pytest.raises(ValueError, match="already exists"):
                await repo.create_table(table_data, created_by=test_user_email)


class TestDocumentRepositoryIntegration:
    """Integration tests for DocumentRepository with real PostgreSQL."""

    @pytest_asyncio.fixture
    async def test_table(self, test_org_id, test_user_email, cleanup_tables):
        """Create a test table for document operations."""
        async with get_db_context() as db:
            repo = TableRepository(db, test_org_id)

            from src.models.contracts.tables import TableCreate
            table_data = TableCreate(
                name=f"test_documents_{uuid4().hex[:8]}",
            )
            table = await repo.create_table(table_data, created_by=test_user_email)
            cleanup_tables.append(table.id)

            # Need to re-fetch from fresh session for document tests
            return table.id, table.name

    @pytest.mark.asyncio
    async def test_insert_and_get_document(self, test_table, test_org_id, test_user_email):
        """Test inserting and retrieving a document."""
        table_id, table_name = test_table

        async with get_db_context() as db:
            # Get table
            table_repo = TableRepository(db, test_org_id)
            table = await table_repo.get_by_name(table_name)
            assert table is not None

            doc_repo = DocumentRepository(db, table)

            # Insert document
            doc_data = {"name": "Acme Corp", "email": "info@acme.com", "status": "active"}
            doc = await doc_repo.insert(doc_data, created_by=test_user_email)

            assert doc.id is not None
            assert doc.data["name"] == "Acme Corp"
            assert doc.created_by == test_user_email

            # Get document
            retrieved = await doc_repo.get(doc.id)
            assert retrieved is not None
            assert retrieved.data["email"] == "info@acme.com"

    @pytest.mark.asyncio
    async def test_update_document(self, test_table, test_org_id, test_user_email):
        """Test updating a document (partial update)."""
        table_id, table_name = test_table

        async with get_db_context() as db:
            table_repo = TableRepository(db, test_org_id)
            table = await table_repo.get_by_name(table_name)
            assert table is not None

            doc_repo = DocumentRepository(db, table)

            # Insert document
            doc = await doc_repo.insert(
                {"name": "Acme", "status": "active"},
                created_by=test_user_email,
            )

            # Update document (partial)
            updated = await doc_repo.update(
                doc.id,
                {"status": "inactive", "notes": "Churned"},
                updated_by=test_user_email,
            )

            assert updated is not None
            assert updated.data["name"] == "Acme"  # Original preserved
            assert updated.data["status"] == "inactive"  # Updated
            assert updated.data["notes"] == "Churned"  # Added

    @pytest.mark.asyncio
    async def test_delete_document(self, test_table, test_org_id, test_user_email):
        """Test deleting a document."""
        table_id, table_name = test_table

        async with get_db_context() as db:
            table_repo = TableRepository(db, test_org_id)
            table = await table_repo.get_by_name(table_name)
            assert table is not None

            doc_repo = DocumentRepository(db, table)

            # Insert document
            doc = await doc_repo.insert({"name": "ToDelete"}, created_by=test_user_email)

            # Delete document
            success = await doc_repo.delete(doc.id)
            assert success is True

            # Verify it's gone
            retrieved = await doc_repo.get(doc.id)
            assert retrieved is None

    @pytest.mark.asyncio
    async def test_query_documents_with_filter(self, test_table, test_org_id, test_user_email):
        """Test querying documents with filter."""
        table_id, table_name = test_table

        async with get_db_context() as db:
            table_repo = TableRepository(db, test_org_id)
            table = await table_repo.get_by_name(table_name)
            assert table is not None

            doc_repo = DocumentRepository(db, table)

            # Insert test documents
            await doc_repo.insert({"name": "Active1", "status": "active"}, created_by=test_user_email)
            await doc_repo.insert({"name": "Active2", "status": "active"}, created_by=test_user_email)
            await doc_repo.insert({"name": "Inactive", "status": "inactive"}, created_by=test_user_email)

            # Query with filter
            from src.models.contracts.tables import DocumentQuery
            query = DocumentQuery(where={"status": "active"})
            documents, total = await doc_repo.query(query)

            assert total == 2
            assert all(d.data["status"] == "active" for d in documents)

    @pytest.mark.asyncio
    async def test_query_documents_with_pagination(self, test_table, test_org_id, test_user_email):
        """Test querying documents with pagination."""
        table_id, table_name = test_table

        async with get_db_context() as db:
            table_repo = TableRepository(db, test_org_id)
            table = await table_repo.get_by_name(table_name)
            assert table is not None

            doc_repo = DocumentRepository(db, table)

            # Insert 10 documents
            for i in range(10):
                await doc_repo.insert({"index": i, "name": f"Doc{i}"}, created_by=test_user_email)

            # Query with pagination
            from src.models.contracts.tables import DocumentQuery
            query = DocumentQuery(limit=3, offset=0)
            documents, total = await doc_repo.query(query)

            assert total == 10
            assert len(documents) == 3

            # Next page
            query = DocumentQuery(limit=3, offset=3)
            documents, total = await doc_repo.query(query)

            assert total == 10
            assert len(documents) == 3

    @pytest.mark.asyncio
    async def test_count_documents(self, test_table, test_org_id, test_user_email):
        """Test counting documents."""
        table_id, table_name = test_table

        async with get_db_context() as db:
            table_repo = TableRepository(db, test_org_id)
            table = await table_repo.get_by_name(table_name)
            assert table is not None

            doc_repo = DocumentRepository(db, table)

            # Insert documents
            await doc_repo.insert({"type": "a"}, created_by=test_user_email)
            await doc_repo.insert({"type": "a"}, created_by=test_user_email)
            await doc_repo.insert({"type": "b"}, created_by=test_user_email)

            # Count all
            total = await doc_repo.count()
            assert total >= 3

            # Count with filter
            count_a = await doc_repo.count(where={"type": "a"})
            assert count_a == 2

            count_b = await doc_repo.count(where={"type": "b"})
            assert count_b == 1


class TestTableCascadeDelete:
    """Test that deleting a table cascades to documents."""

    @pytest.mark.asyncio
    async def test_delete_table_deletes_documents(self, test_org_id, test_user_email):
        """Test that deleting a table also deletes all its documents."""
        async with get_db_context() as db:
            table_repo = TableRepository(db, test_org_id)

            from src.models.contracts.tables import TableCreate
            table_data = TableCreate(name=f"test_cascade_{uuid4().hex[:8]}")
            table = await table_repo.create_table(table_data, created_by=test_user_email)

            doc_repo = DocumentRepository(db, table)

            # Insert documents
            doc1 = await doc_repo.insert({"name": "Doc1"}, created_by=test_user_email)
            doc2 = await doc_repo.insert({"name": "Doc2"}, created_by=test_user_email)
            doc_ids = [doc1.id, doc2.id]

            # Delete table
            success = await table_repo.delete_table(table_data.name)
            assert success is True

            # Verify documents are gone
            stmt = select(Document).where(Document.id.in_(doc_ids))
            result = await db.execute(stmt)
            remaining = result.scalars().all()
            assert len(remaining) == 0
