"""
Knowledge Repository

Data access layer for the knowledge store (RAG).
Handles vector storage, semantic search, and namespace management.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from src.models.orm import KnowledgeStore
from src.repositories.base import BaseRepository


@dataclass
class KnowledgeDocument:
    """Document returned from knowledge store."""

    id: str
    namespace: str
    content: str
    metadata: dict[str, Any]
    score: float | None = None
    organization_id: str | None = None
    key: str | None = None
    created_at: datetime | None = None


@dataclass
class NamespaceInfo:
    """Information about a namespace."""

    namespace: str
    scopes: dict[str, int]  # {"global": count, "org": count, "total": count}


class KnowledgeRepository(BaseRepository[KnowledgeStore]):
    """
    Repository for knowledge store operations.

    Supports:
    - Upsert by key for easy re-indexing
    - Org-scoped storage with global fallback
    - Vector similarity search
    - Metadata filtering
    """

    model = KnowledgeStore

    async def store(
        self,
        content: str,
        embedding: list[float],
        namespace: str = "default",
        key: str | None = None,
        metadata: dict[str, Any] | None = None,
        organization_id: UUID | None = None,
        created_by: UUID | None = None,
    ) -> str:
        """
        Store a document with its embedding.

        If key is provided and exists, updates the existing document (upsert).

        Args:
            content: Text content
            embedding: Vector embedding
            namespace: Namespace for organization
            key: Optional user-provided key for upserts
            metadata: Optional metadata dict
            organization_id: Organization scope (None for global)
            created_by: User who created the document

        Returns:
            Document ID (UUID as string)
        """
        if key:
            # Use upsert for key-based storage
            # Build values dict using column objects to avoid SQLAlchemy MetaData conflict
            # (the column is named 'metadata' which conflicts with SQLAlchemy's MetaData class)
            metadata_col = KnowledgeStore.__table__.c.metadata
            values = {
                KnowledgeStore.namespace: namespace,
                KnowledgeStore.organization_id: organization_id,
                KnowledgeStore.key: key,
                KnowledgeStore.content: content,
                metadata_col: metadata or {},
                KnowledgeStore.embedding: embedding,
                KnowledgeStore.created_by: created_by,
            }
            stmt = insert(KnowledgeStore).values(values)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_knowledge_ns_org_key",
                set_={
                    "content": stmt.excluded.content,
                    "metadata": stmt.excluded.metadata,
                    "embedding": stmt.excluded.embedding,
                    "updated_at": func.now(),
                },
            )
            stmt = stmt.returning(KnowledgeStore.id)
            result = await self.session.execute(stmt)
            doc_id = result.scalar_one()
            return str(doc_id)
        else:
            # No key - just insert
            doc = KnowledgeStore(
                namespace=namespace,
                organization_id=organization_id,
                content=content,
                doc_metadata=metadata or {},
                embedding=embedding,
                created_by=created_by,
            )
            self.session.add(doc)
            await self.session.flush()
            return str(doc.id)

    async def search(
        self,
        query_embedding: list[float],
        namespace: str | list[str],
        organization_id: UUID | None = None,
        limit: int = 5,
        min_score: float | None = None,
        metadata_filter: dict[str, Any] | None = None,
        fallback: bool = True,
    ) -> list[KnowledgeDocument]:
        """
        Search for similar documents using vector similarity.

        Args:
            query_embedding: Query vector
            namespace: Namespace(s) to search
            organization_id: Organization scope
            limit: Maximum results
            min_score: Minimum similarity score (0-1)
            metadata_filter: Filter by metadata fields
            fallback: If True, also search global scope

        Returns:
            List of KnowledgeDocument sorted by similarity
        """
        namespaces = [namespace] if isinstance(namespace, str) else namespace

        # Build the query
        # We use cosine distance (1 - cosine_similarity), so lower is better
        # Convert to similarity score: 1 - distance
        distance_expr = KnowledgeStore.embedding.cosine_distance(query_embedding)
        score_expr = (1 - distance_expr).label("score")

        stmt = select(
            KnowledgeStore,
            score_expr,
        ).where(
            KnowledgeStore.namespace.in_(namespaces)
        )

        # Organization scoping with optional fallback
        if organization_id and fallback:
            # Search both org and global
            stmt = stmt.where(
                (KnowledgeStore.organization_id == organization_id) |
                (KnowledgeStore.organization_id.is_(None))
            )
        elif organization_id:
            # Only org scope
            stmt = stmt.where(KnowledgeStore.organization_id == organization_id)
        else:
            # Only global scope
            stmt = stmt.where(KnowledgeStore.organization_id.is_(None))

        # Metadata filtering using JSONB containment
        if metadata_filter:
            for key, value in metadata_filter.items():
                # Use @> containment operator
                stmt = stmt.where(
                    KnowledgeStore.doc_metadata.contains({key: value})
                )

        # Order by similarity (higher score = more similar)
        stmt = stmt.order_by(score_expr.desc())
        stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        rows = result.all()

        documents = []
        for row in rows:
            doc = row[0]
            score = row[1]

            # Filter by min_score if specified
            if min_score is not None and score < min_score:
                continue

            documents.append(
                KnowledgeDocument(
                    id=str(doc.id),
                    namespace=doc.namespace,
                    content=doc.content,
                    metadata=doc.doc_metadata,
                    score=float(score),
                    organization_id=str(doc.organization_id) if doc.organization_id else None,
                    key=doc.key,
                    created_at=doc.created_at,
                )
            )

        return documents

    async def delete_by_key(
        self,
        key: str,
        namespace: str,
        organization_id: UUID | None = None,
    ) -> bool:
        """
        Delete a document by key.

        Args:
            key: Document key
            namespace: Namespace
            organization_id: Organization scope (None for global)

        Returns:
            True if deleted, False if not found
        """
        stmt = delete(KnowledgeStore).where(
            KnowledgeStore.key == key,
            KnowledgeStore.namespace == namespace,
        )

        if organization_id:
            stmt = stmt.where(KnowledgeStore.organization_id == organization_id)
        else:
            stmt = stmt.where(KnowledgeStore.organization_id.is_(None))

        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def delete_namespace(
        self,
        namespace: str,
        organization_id: UUID | None = None,
    ) -> int:
        """
        Delete all documents in a namespace.

        Args:
            namespace: Namespace to delete
            organization_id: Organization scope (None for global)

        Returns:
            Number of documents deleted
        """
        stmt = delete(KnowledgeStore).where(
            KnowledgeStore.namespace == namespace,
        )

        if organization_id:
            stmt = stmt.where(KnowledgeStore.organization_id == organization_id)
        else:
            stmt = stmt.where(KnowledgeStore.organization_id.is_(None))

        result = await self.session.execute(stmt)
        return result.rowcount

    async def list_namespaces(
        self,
        organization_id: UUID | None = None,
        include_global: bool = True,
    ) -> list[NamespaceInfo]:
        """
        List all namespaces with document counts per scope.

        Args:
            organization_id: If provided, include org-scoped counts
            include_global: If True, include global namespaces

        Returns:
            List of NamespaceInfo with scope counts
        """
        # This is a bit complex - we need to get counts grouped by namespace and org_id
        stmt = select(
            KnowledgeStore.namespace,
            KnowledgeStore.organization_id,
            func.count(KnowledgeStore.id).label("count"),
        ).group_by(
            KnowledgeStore.namespace,
            KnowledgeStore.organization_id,
        )

        # Filter by what we want to see
        if organization_id and include_global:
            stmt = stmt.where(
                (KnowledgeStore.organization_id == organization_id) |
                (KnowledgeStore.organization_id.is_(None))
            )
        elif organization_id:
            stmt = stmt.where(KnowledgeStore.organization_id == organization_id)
        elif include_global:
            stmt = stmt.where(KnowledgeStore.organization_id.is_(None))

        result = await self.session.execute(stmt)
        rows = result.all()

        # Aggregate by namespace
        namespace_data: dict[str, dict[str, int]] = {}
        for row in rows:
            ns = row[0]
            org_id = row[1]
            count = row[2]

            if ns not in namespace_data:
                namespace_data[ns] = {"global": 0, "org": 0, "total": 0}

            if org_id is None:
                namespace_data[ns]["global"] = count
            else:
                namespace_data[ns]["org"] = count

            namespace_data[ns]["total"] += count

        return [
            NamespaceInfo(namespace=ns, scopes=scopes)
            for ns, scopes in sorted(namespace_data.items())
        ]

    async def get_by_key(
        self,
        key: str,
        namespace: str,
        organization_id: UUID | None = None,
    ) -> KnowledgeDocument | None:
        """
        Get a document by its key.

        Args:
            key: Document key
            namespace: Namespace
            organization_id: Organization scope (None for global)

        Returns:
            KnowledgeDocument or None if not found
        """
        stmt = select(KnowledgeStore).where(
            KnowledgeStore.key == key,
            KnowledgeStore.namespace == namespace,
        )

        if organization_id:
            stmt = stmt.where(KnowledgeStore.organization_id == organization_id)
        else:
            stmt = stmt.where(KnowledgeStore.organization_id.is_(None))

        result = await self.session.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        return KnowledgeDocument(
            id=str(doc.id),
            namespace=doc.namespace,
            content=doc.content,
            metadata=doc.doc_metadata,
            organization_id=str(doc.organization_id) if doc.organization_id else None,
            key=doc.key,
            created_at=doc.created_at,
        )
