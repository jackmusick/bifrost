# Phase 2: Database Schema

## Overview

Add `content` column to `workspace_files` table for storing Python module source code.

## Migration

**File:** `api/alembic/versions/YYYYMMDD_add_workspace_content.py`

```python
"""Add content column to workspace_files for module storage

Revision ID: xxxxx
Revises: xxxxx
Create Date: YYYY-MM-DD
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


def upgrade():
    # Add content column for storing Python module source code
    op.add_column(
        'workspace_files',
        sa.Column('content', sa.Text(), nullable=True)
    )

    # Partial index for efficient module lookups
    # Only indexes rows where entity_type='module' AND NOT is_deleted
    op.create_index(
        'ix_workspace_files_modules',
        'workspace_files',
        ['path'],
        postgresql_where=text("entity_type = 'module' AND NOT is_deleted")
    )


def downgrade():
    op.drop_index('ix_workspace_files_modules', table_name='workspace_files')
    op.drop_column('workspace_files', 'content')
```

## ORM Model Update

**File:** `api/src/models/orm/workspace.py`

```python
from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

class WorkspaceFile(Base):
    __tablename__ = "workspace_files"

    # ... existing columns ...

    # NEW: Content storage for modules
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
```

## PostgreSQL TEXT Column

PostgreSQL's `TEXT` type supports up to 1GB of content. For our use case:

- Typical module: 1-50 KB
- Large module: 100-500 KB
- Extreme edge case: 4 MB

No practical limit concerns. TEXT is the correct choice (vs VARCHAR with length limit).

## Index Strategy

The partial index `ix_workspace_files_modules` is optimized for the virtual import hook's query pattern:

```sql
SELECT content FROM workspace_files
WHERE path = ? AND entity_type = 'module' AND NOT is_deleted
```

Benefits:
- Only indexes module rows (not workflows, forms, apps, agents)
- Excludes soft-deleted rows
- Small index size, fast lookups
