# User-Created Agents + Knowledge Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let any authenticated user create private AI agents using tools and knowledge available through their roles, and add a Knowledge management page so knowledge sources become first-class role-assignable entities.

**Architecture:** Two interlocking features. Part A adds `private` access level + `owner_user_id` to agents, loosens API permissions so non-admins can create/edit/delete their own private agents, and adds a promote-to-org flow. Part B creates a `KnowledgeSource` entity with role-based access (mirroring `WorkflowRole`), a CRUD API, and a frontend page with tiptap markdown editing. Both share a single alembic migration and a `permissions` JSONB column on roles.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0, PostgreSQL (pgvector), Alembic, React, TypeScript, shadcn/ui, tiptap

---

## Task 1: Alembic Migration

**Files:**
- Create: `api/alembic/versions/20260208_user_agents_knowledge.py`

**Step 1: Create the migration file**

```python
"""user_agents_knowledge

Add private agent access level, owner_user_id, role permissions JSONB,
knowledge_sources table, and knowledge_source_roles junction table.

Revision ID: a1b2c3d4e5f6
Revises: d4f6a8b05e23
Create Date: 2026-02-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'd4f6a8b05e23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add 'private' to agent_access_level enum
    # Must use raw connection + autocommit for enum changes
    conn = op.get_bind()
    conn.execute(sa.text("COMMIT"))
    conn.execute(sa.text("ALTER TYPE agent_access_level ADD VALUE IF NOT EXISTS 'private'"))

    # 2. Add owner_user_id to agents
    op.add_column('agents', sa.Column('owner_user_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=True))
    op.create_index('ix_agents_owner_user_id', 'agents', ['owner_user_id'])

    # 3. Add permissions JSONB to roles
    op.add_column('roles', sa.Column('permissions', JSONB, nullable=False, server_default='{}'))

    # 4. Create knowledge_sources table
    op.create_table(
        'knowledge_sources',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('namespace', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('access_level', sa.Enum('authenticated', 'role_based', name='knowledge_source_access_level', create_type=True), nullable=False, server_default='role_based'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('document_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_by', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('ix_knowledge_sources_organization_id', 'knowledge_sources', ['organization_id'])
    op.create_index('ix_knowledge_sources_namespace_org', 'knowledge_sources', ['namespace', 'organization_id'], unique=True)

    # 5. Create knowledge_source_roles junction table
    op.create_table(
        'knowledge_source_roles',
        sa.Column('knowledge_source_id', sa.Uuid(), sa.ForeignKey('knowledge_sources.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('role_id', sa.Uuid(), sa.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('assigned_by', sa.String(255), nullable=True),
        sa.Column('assigned_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('ix_knowledge_source_roles_role_id', 'knowledge_source_roles', ['role_id'])


def downgrade() -> None:
    op.drop_table('knowledge_source_roles')
    op.drop_table('knowledge_sources')
    op.drop_column('roles', 'permissions')
    op.drop_index('ix_agents_owner_user_id', table_name='agents')
    op.drop_column('agents', 'owner_user_id')
    # Note: Cannot remove enum value in PostgreSQL
```

**Step 2: Verify the migration applies**

Run: `docker restart bifrost-dev-init-1` (applies migration), then `docker restart bifrost-dev-api-1`
Expected: Containers restart without errors. Check logs: `docker logs bifrost-dev-init-1 --tail 20`

**Step 3: Commit**

```bash
git add api/alembic/versions/20260208_user_agents_knowledge.py
git commit -m "feat: add migration for private agents, role permissions, knowledge sources"
```

---

## Task 2: Enum + ORM Model Changes (Agent, Role)

**Files:**
- Modify: `api/src/models/enums.py:77-81`
- Modify: `api/src/models/orm/agents.py:25-98`
- Modify: `api/src/models/orm/users.py:85-116`
- Modify: `api/src/models/orm/__init__.py`

**Step 1: Add PRIVATE to AgentAccessLevel enum**

In `api/src/models/enums.py`, add after line 80:

```python
class AgentAccessLevel(str, Enum):
    """Agent access control levels"""
    AUTHENTICATED = "authenticated"
    ROLE_BASED = "role_based"
    PRIVATE = "private"
```

**Step 2: Add owner_user_id to Agent ORM**

In `api/src/models/orm/agents.py`, add after the `organization_id` column (line 46):

```python
    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), default=None
    )
```

Add relationship after the `organization` relationship (line 73):

```python
    owner: Mapped["User | None"] = relationship(foreign_keys=[owner_user_id])
```

Add to `__table_args__` tuple:

```python
    Index("ix_agents_owner_user_id", "owner_user_id"),
```

Add `User` to the TYPE_CHECKING imports if not already there.

**Step 3: Add permissions JSONB to Role ORM**

In `api/src/models/orm/users.py`, add to the `Role` class after `description` (line 96):

```python
    permissions: Mapped[dict] = mapped_column(JSONB, default={}, server_default='{}')
```

Add `JSONB` to the sqlalchemy.dialects.postgresql import:
```python
from sqlalchemy.dialects.postgresql import JSONB
```

**Step 4: Verify types pass**

Run: `cd /home/jack/GitHub/bifrost/api && python -c "from src.models.orm.agents import Agent; from src.models.orm.users import Role; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add api/src/models/enums.py api/src/models/orm/agents.py api/src/models/orm/users.py
git commit -m "feat: add PRIVATE access level, owner_user_id on Agent, permissions on Role"
```

---

## Task 3: KnowledgeSource + KnowledgeSourceRole ORM Models

**Files:**
- Create: `api/src/models/orm/knowledge_sources.py`
- Modify: `api/src/models/orm/__init__.py`

**Step 1: Create KnowledgeSource ORM**

Create `api/src/models/orm/knowledge_sources.py`:

```python
"""
KnowledgeSource and KnowledgeSourceRole ORM models.

Represents first-class knowledge source entities with role-based access control,
following the same pattern as WorkflowRole, AgentRole, FormRole.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.organizations import Organization
    from src.models.orm.users import Role


class KnowledgeSource(Base):
    """Knowledge source entity — a named, scoped knowledge namespace."""

    __tablename__ = "knowledge_sources"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    namespace: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), default=None
    )
    access_level: Mapped[str] = mapped_column(
        ENUM("authenticated", "role_based", name="knowledge_source_access_level", create_type=False),
        default="role_based",
        server_default="role_based",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    document_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )

    # Relationships
    organization: Mapped["Organization | None"] = relationship()
    roles: Mapped[list["Role"]] = relationship(
        secondary="knowledge_source_roles",
    )

    __table_args__ = (
        Index("ix_knowledge_sources_organization_id", "organization_id"),
        Index("ix_knowledge_sources_namespace_org", "namespace", "organization_id", unique=True),
    )

    @property
    def role_ids(self) -> list[str]:
        return [str(r.id) for r in self.roles]


class KnowledgeSourceRole(Base):
    """Knowledge source to role junction table."""

    __tablename__ = "knowledge_source_roles"

    knowledge_source_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_by: Mapped[str | None] = mapped_column(String(255), default=None)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )

    __table_args__ = (
        Index("ix_knowledge_source_roles_role_id", "role_id"),
    )
```

**Step 2: Export from `__init__.py`**

In `api/src/models/orm/__init__.py`, add:

Import line:
```python
from src.models.orm.knowledge_sources import KnowledgeSource, KnowledgeSourceRole
```

Add to `__all__`:
```python
    # Knowledge Sources
    "KnowledgeSource",
    "KnowledgeSourceRole",
```

**Step 3: Verify import**

Run: `cd /home/jack/GitHub/bifrost/api && python -c "from src.models.orm import KnowledgeSource, KnowledgeSourceRole; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add api/src/models/orm/knowledge_sources.py api/src/models/orm/__init__.py
git commit -m "feat: add KnowledgeSource and KnowledgeSourceRole ORM models"
```

---

## Task 4: Pydantic Contract Changes (Agents + Roles)

**Files:**
- Modify: `api/src/models/contracts/agents.py:79-135`
- Modify: `api/src/models/contracts/users.py:130-176`

**Step 1: Update AgentPublic**

In `api/src/models/contracts/agents.py`, add to `AgentPublic` after `created_by`:

```python
    owner_user_id: UUID | None = None
    owner_email: str | None = None
```

Update the existing `serialize_uuid` serializer to include `owner_user_id`:

```python
    @field_serializer("id", "organization_id", "owner_user_id")
    def serialize_uuid(self, v: UUID | None) -> str | None:
        return str(v) if v else None
```

**Step 2: Update AgentSummary**

Add to `AgentSummary`:

```python
    owner_user_id: UUID | None = None
```

Update its UUID serializer:

```python
    @field_serializer("id", "organization_id", "owner_user_id")
    def serialize_uuid(self, v: UUID | None) -> str | None:
        return str(v) if v else None
```

**Step 3: Add AgentPromoteRequest**

Add after `AgentUpdate`:

```python
class AgentPromoteRequest(BaseModel):
    """Request to promote a private agent to organization scope."""
    access_level: AgentAccessLevel = Field(
        default=AgentAccessLevel.ROLE_BASED,
        description="Target access level (authenticated or role_based)"
    )
    role_ids: list[str] = Field(
        default_factory=list,
        description="Role IDs for role_based access"
    )
```

**Step 4: Update Role contracts**

In `api/src/models/contracts/users.py`:

Add `permissions` to `Role` class:
```python
    permissions: dict = Field(default_factory=dict)
```

Add `permissions` to `RolePublic`:
```python
    permissions: dict = Field(default_factory=dict)
```

Add `permissions` to `CreateRoleRequest`:
```python
    permissions: dict | None = Field(default=None)
```

Add `permissions` to `UpdateRoleRequest`:
```python
    permissions: dict | None = Field(default=None)
```

**Step 5: Commit**

```bash
git add api/src/models/contracts/agents.py api/src/models/contracts/users.py
git commit -m "feat: add owner fields to agent contracts, permissions to role contracts"
```

---

## Task 5: Knowledge Source Contracts

**Files:**
- Create: `api/src/models/contracts/knowledge.py`

**Step 1: Create knowledge contracts**

Create `api/src/models/contracts/knowledge.py`:

```python
"""
Knowledge source and document contract models for Bifrost.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer


# ==================== KNOWLEDGE SOURCE MODELS ====================


class KnowledgeSourceCreate(BaseModel):
    """Request model for creating a knowledge source."""
    name: str = Field(..., min_length=1, max_length=255)
    namespace: str | None = Field(default=None, max_length=255, description="Namespace key (auto-generated from name if omitted)")
    description: str | None = Field(default=None, max_length=2000)
    organization_id: UUID | None = Field(default=None, description="Organization ID (null = global)")
    access_level: str = Field(default="role_based", description="authenticated or role_based")
    role_ids: list[str] = Field(default_factory=list, description="Role IDs for role_based access")


class KnowledgeSourceUpdate(BaseModel):
    """Request model for updating a knowledge source."""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    access_level: str | None = None
    is_active: bool | None = None
    role_ids: list[str] | None = None


class KnowledgeSourcePublic(BaseModel):
    """Knowledge source output for API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    namespace: str
    description: str | None = None
    organization_id: UUID | None = None
    access_level: str
    is_active: bool
    document_count: int = 0
    role_ids: list[str] = Field(default_factory=list)
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_serializer("id", "organization_id")
    def serialize_uuid(self, v: UUID | None) -> str | None:
        return str(v) if v else None

    @field_serializer("created_at", "updated_at")
    def serialize_dt(self, dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None


class KnowledgeSourceSummary(BaseModel):
    """Lightweight knowledge source summary for listings."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    namespace: str
    description: str | None = None
    organization_id: UUID | None = None
    access_level: str
    is_active: bool
    document_count: int = 0
    created_at: datetime

    @field_serializer("id", "organization_id")
    def serialize_uuid(self, v: UUID | None) -> str | None:
        return str(v) if v else None

    @field_serializer("created_at")
    def serialize_dt(self, dt: datetime) -> str:
        return dt.isoformat()


# ==================== KNOWLEDGE DOCUMENT MODELS ====================


class KnowledgeDocumentCreate(BaseModel):
    """Request model for creating a knowledge document."""
    content: str = Field(..., min_length=1, max_length=500000, description="Markdown content")
    key: str | None = Field(default=None, max_length=255, description="Optional key for upsert")
    metadata: dict = Field(default_factory=dict)


class KnowledgeDocumentUpdate(BaseModel):
    """Request model for updating a knowledge document."""
    content: str = Field(..., min_length=1, max_length=500000, description="Markdown content")
    metadata: dict | None = None


class KnowledgeDocumentPublic(BaseModel):
    """Knowledge document output for API responses."""

    id: str
    namespace: str
    key: str | None = None
    content: str
    metadata: dict = Field(default_factory=dict)
    organization_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class KnowledgeDocumentSummary(BaseModel):
    """Lightweight document summary (no full content)."""

    id: str
    namespace: str
    key: str | None = None
    content_preview: str = Field(default="", description="First ~200 chars of content")
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None
```

**Step 2: Commit**

```bash
git add api/src/models/contracts/knowledge.py
git commit -m "feat: add knowledge source and document Pydantic contracts"
```

---

## Task 6: Repository Changes (OrgScoped + Agents + KnowledgeSources)

**Files:**
- Modify: `api/src/repositories/org_scoped.py:281-322`
- Modify: `api/src/repositories/agents.py:33-69`
- Create: `api/src/repositories/knowledge_sources.py`

**Step 1: Add `private` access level to OrgScopedRepository**

In `api/src/repositories/org_scoped.py`, in `_can_access_entity`, after the `role_based` check (line ~319):

```python
        if access_level == "private":
            entity_owner_id = getattr(entity, "owner_user_id", None)
            return entity_owner_id is not None and entity_owner_id == self.user_id
```

**Step 2: Update AgentRepository.list_agents to include private agents**

In `api/src/repositories/agents.py`, replace the `list_agents` method body. The key change is expanding the WHERE clause to include private agents owned by the current user:

```python
    async def list_agents(
        self,
        active_only: bool = True,
    ) -> list[Agent]:
        """List agents with cascade scoping, role-based access, and user's private agents."""
        from sqlalchemy import or_
        from src.models.enums import AgentAccessLevel

        query = select(self.model).options(selectinload(self.model.tools))

        # Build scope filter: cascade (org + global) OR user's own private agents
        cascade_conditions = []
        if self.org_id is not None:
            cascade_conditions.append(self.model.organization_id == self.org_id)
        cascade_conditions.append(self.model.organization_id.is_(None))

        private_condition = (
            (self.model.access_level == AgentAccessLevel.PRIVATE) &
            (self.model.owner_user_id == self.user_id)
        ) if self.user_id else None

        if private_condition is not None:
            query = query.where(or_(*cascade_conditions, private_condition))
        else:
            query = query.where(or_(*cascade_conditions))

        if active_only:
            query = query.where(self.model.is_active.is_(True))

        query = query.order_by(self.model.name)

        result = await self.session.execute(query)
        entities = list(result.scalars().unique().all())

        # Filter by role access for non-superusers
        if not self.is_superuser:
            accessible = []
            for entity in entities:
                if await self._can_access_entity(entity):
                    accessible.append(entity)
            return accessible

        return entities
```

Also update `get_agent_with_access_check` to handle private agents — after the org-specific and global checks, try finding the agent if it's private and owned by the current user:

```python
    async def get_agent_with_access_check(self, agent_id: UUID) -> Agent | None:
        """Get agent by ID with cascade scoping, role-based access check, and private ownership."""
        query = (
            select(self.model)
            .options(
                selectinload(self.model.tools),
                selectinload(self.model.delegated_agents),
                selectinload(self.model.roles),
            )
            .where(self.model.id == agent_id)
        )

        # Try org-specific first
        if self.org_id is not None:
            org_query = query.where(self.model.organization_id == self.org_id)
            result = await self.session.execute(org_query)
            entity = result.scalar_one_or_none()
            if entity:
                if await self._can_access_entity(entity):
                    return entity
                return None

        # Fall back to global
        global_query = query.where(self.model.organization_id.is_(None))
        result = await self.session.execute(global_query)
        entity = result.scalar_one_or_none()

        if entity and await self._can_access_entity(entity):
            return entity
        return None
```

Note: Private agents have `organization_id` set to the user's org, so the existing org-specific query will find them. The `_can_access_entity` now handles the `private` check correctly.

**Step 3: Create KnowledgeSourceRepository**

Create `api/src/repositories/knowledge_sources.py`:

```python
"""
Knowledge Source Repository

Repository for KnowledgeSource CRUD with organization scoping and role-based access.
"""

from src.models.orm.knowledge_sources import KnowledgeSource, KnowledgeSourceRole
from src.repositories.org_scoped import OrgScopedRepository


class KnowledgeSourceRepository(OrgScopedRepository[KnowledgeSource]):
    """
    Knowledge source repository using OrgScopedRepository.

    Uses CASCADE scoping (org + global) and role-based access control
    via the knowledge_source_roles junction table.
    """

    model = KnowledgeSource
    role_table = KnowledgeSourceRole
    role_entity_id_column = "knowledge_source_id"
```

**Step 4: Verify imports**

Run: `cd /home/jack/GitHub/bifrost/api && python -c "from src.repositories.knowledge_sources import KnowledgeSourceRepository; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add api/src/repositories/org_scoped.py api/src/repositories/agents.py api/src/repositories/knowledge_sources.py
git commit -m "feat: add private access level to repos, KnowledgeSourceRepository"
```

---

## Task 7: Agent API Endpoint Changes

**Files:**
- Modify: `api/src/routers/agents.py`

This is the largest task. The key changes are:
1. Loosen `create_agent`, `update_agent`, `delete_agent` from `CurrentSuperuser` to `CurrentActiveUser` with inline authorization.
2. Add `_validate_user_tool_access`, `_user_has_permission` helpers.
3. Add `POST /agents/{id}/promote` and `GET /agents/accessible-tools` and `GET /agents/accessible-knowledge` endpoints.
4. Update `_agent_to_public` for owner fields.

**Step 1: Add helper functions**

Add after `_validate_agent_references`:

```python
async def _validate_user_tool_access(
    db: DbSession,
    user_id: UUID,
    tool_ids: list[str],
) -> None:
    """Validate user can access all specified tools via their roles."""
    if not tool_ids:
        return

    from src.models.orm.users import UserRole
    from src.models.orm.workflow_roles import WorkflowRole

    # Get user's role IDs
    result = await db.execute(
        select(UserRole.role_id).where(UserRole.user_id == user_id)
    )
    user_role_ids = set(result.scalars().all())

    for tool_id in tool_ids:
        try:
            workflow_uuid = UUID(tool_id)
        except ValueError:
            raise HTTPException(422, f"Invalid tool ID: {tool_id}")

        # Get workflow's role IDs
        result = await db.execute(
            select(WorkflowRole.role_id).where(WorkflowRole.workflow_id == workflow_uuid)
        )
        workflow_role_ids = set(result.scalars().all())

        # If workflow has roles, user must share at least one
        if workflow_role_ids and not workflow_role_ids.intersection(user_role_ids):
            result = await db.execute(select(Workflow.name).where(Workflow.id == workflow_uuid))
            name = result.scalar_one_or_none() or tool_id
            raise HTTPException(403, f"You do not have role access to tool '{name}'")


async def _user_has_permission(
    db: DbSession,
    user_id: UUID,
    permission: str,
) -> bool:
    """Check if a user has a permission via any of their roles."""
    from src.models.orm.users import UserRole

    result = await db.execute(
        select(Role.permissions)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
        .where(Role.is_active.is_(True))
    )
    for permissions in result.scalars().all():
        if permissions and permissions.get(permission):
            return True
    return False
```

**Step 2: Update `_agent_to_public`**

Add owner fields:

```python
def _agent_to_public(agent: Agent) -> AgentPublic:
    valid_system_tool_ids = set(get_system_tool_ids())

    owner_email = None
    if agent.owner_user_id and hasattr(agent, 'owner') and agent.owner:
        owner_email = agent.owner.email

    return AgentPublic(
        id=agent.id,
        name=agent.name,
        description=agent.description,
        system_prompt=agent.system_prompt,
        channels=agent.channels,
        access_level=agent.access_level,
        organization_id=agent.organization_id,
        is_active=agent.is_active,
        is_system=agent.is_system,
        created_by=agent.created_by,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        owner_user_id=agent.owner_user_id,
        owner_email=owner_email,
        tool_ids=[str(t.id) for t in agent.tools],
        delegated_agent_ids=[str(a.id) for a in agent.delegated_agents],
        role_ids=[str(r.id) for r in agent.roles],
        knowledge_sources=agent.knowledge_sources or [],
        system_tools=[t for t in (agent.system_tools or []) if t in valid_system_tool_ids],
        llm_model=agent.llm_model,
        llm_max_tokens=agent.llm_max_tokens,
        llm_temperature=agent.llm_temperature,
    )
```

Eagerly load `owner` in queries where `_agent_to_public` is called — add `selectinload(Agent.owner)` to the relevant queries.

**Step 3: Update `create_agent` endpoint**

Change `user: CurrentSuperuser` to `user: CurrentActiveUser`. Add authorization:

```python
@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent(
    agent_data: AgentCreate,
    db: DbSession,
    user: CurrentActiveUser,
) -> AgentPublic:
    is_admin = user.is_superuser or any(
        role in ["Platform Admin", "Platform Owner"] for role in user.roles
    )

    if not is_admin:
        # Non-admin: enforce private-only creation
        if agent_data.access_level != AgentAccessLevel.PRIVATE:
            raise HTTPException(403, "Non-admin users can only create private agents")
        # Force org to user's org
        agent_data.organization_id = user.organization_id
        # Validate tool access via roles
        await _validate_user_tool_access(db, user.user_id, agent_data.tool_ids)
        # Block admin-only fields
        agent_data.system_tools = []
        agent_data.knowledge_sources = []
        agent_data.delegated_agent_ids = []
        agent_data.role_ids = []

    # ... rest of existing creation logic ...

    # Set owner for private agents
    owner_user_id = None
    if agent_data.access_level == AgentAccessLevel.PRIVATE:
        owner_user_id = user.user_id

    agent = Agent(
        # ... existing fields ...
        owner_user_id=owner_user_id,
        # ...
    )
```

**Step 4: Update `update_agent` endpoint**

Change `user: CurrentSuperuser` to `user: CurrentActiveUser`. Add authorization:

```python
@router.put("/{agent_id}")
async def update_agent(
    agent_id: UUID,
    agent_data: AgentUpdate,
    db: DbSession,
    user: CurrentActiveUser,
) -> AgentPublic:
    # ... load agent ...

    is_admin = user.is_superuser or any(
        role in ["Platform Admin", "Platform Owner"] for role in user.roles
    )

    if not is_admin:
        if agent.owner_user_id != user.user_id or agent.access_level != AgentAccessLevel.PRIVATE:
            raise HTTPException(403, "You can only edit your own private agents")
        if agent_data.access_level is not None and agent_data.access_level != AgentAccessLevel.PRIVATE:
            raise HTTPException(403, "Use the promote endpoint to change access level")
        if agent_data.tool_ids is not None:
            await _validate_user_tool_access(db, user.user_id, agent_data.tool_ids)
        # Block admin-only fields
        agent_data.system_tools = None
        agent_data.knowledge_sources = None
        agent_data.delegated_agent_ids = None
        agent_data.role_ids = None

    # ... rest of existing update logic ...
```

**Step 5: Update `delete_agent` endpoint**

```python
@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: UUID,
    db: DbSession,
    user: CurrentActiveUser,
) -> None:
    # ... load agent ...

    is_admin = user.is_superuser or any(
        role in ["Platform Admin", "Platform Owner"] for role in user.roles
    )

    if not is_admin:
        if agent.owner_user_id != user.user_id:
            raise HTTPException(403, "You can only delete your own private agents")

    agent.is_active = False
    agent.updated_at = datetime.utcnow()
    await db.flush()
```

**Step 6: Add promote endpoint**

```python
@router.post("/{agent_id}/promote")
async def promote_agent(
    agent_id: UUID,
    request: AgentPromoteRequest,
    db: DbSession,
    user: CurrentActiveUser,
) -> AgentPublic:
    """Promote a private agent to organization scope."""
    result = await db.execute(
        select(Agent)
        .options(
            selectinload(Agent.tools),
            selectinload(Agent.delegated_agents),
            selectinload(Agent.roles),
            selectinload(Agent.owner),
        )
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, f"Agent {agent_id} not found")

    if agent.access_level != AgentAccessLevel.PRIVATE:
        raise HTTPException(400, "Agent is not private — nothing to promote")

    is_admin = user.is_superuser or any(
        role in ["Platform Admin", "Platform Owner"] for role in user.roles
    )

    if not is_admin:
        if agent.owner_user_id != user.user_id:
            raise HTTPException(403, "You can only promote your own agents")
        if not await _user_has_permission(db, user.user_id, "can_promote_agent"):
            raise HTTPException(403, "You do not have permission to promote agents")

    # Promote: change access_level, clear owner
    agent.access_level = request.access_level
    agent.owner_user_id = None
    agent.updated_at = datetime.utcnow()

    # Set roles if role_based
    if request.access_level == AgentAccessLevel.ROLE_BASED and request.role_ids:
        await db.execute(delete(AgentRole).where(AgentRole.agent_id == agent_id))
        for role_id in request.role_ids:
            try:
                role_uuid = UUID(role_id)
                result = await db.execute(
                    select(Role).where(Role.id == role_uuid).where(Role.is_active.is_(True))
                )
                role = result.scalar_one_or_none()
                if role:
                    db.add(AgentRole(agent_id=agent_id, role_id=role.id, assigned_by=user.email))
            except ValueError:
                pass

    await db.flush()

    # Reload
    result = await db.execute(
        select(Agent)
        .options(
            selectinload(Agent.tools),
            selectinload(Agent.delegated_agents),
            selectinload(Agent.roles),
            selectinload(Agent.owner),
        )
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one()
    return _agent_to_public(agent)
```

Import `AgentPromoteRequest` at the top of the file.

**Step 7: Add accessible-tools endpoint**

Note: This must be defined BEFORE the `/{agent_id}` route to avoid path conflicts.

```python
@router.get("/accessible-tools")
async def get_accessible_tools(
    db: DbSession,
    user: CurrentActiveUser,
) -> list[dict]:
    """Get tools the current user can assign to their agents (via role intersection)."""
    from src.models.orm.users import UserRole
    from src.models.orm.workflow_roles import WorkflowRole

    result = await db.execute(
        select(UserRole.role_id).where(UserRole.user_id == user.user_id)
    )
    role_ids = list(result.scalars().all())

    if not role_ids:
        return []

    # Workflows with type='tool', active, sharing at least one role with user
    result = await db.execute(
        select(Workflow)
        .join(WorkflowRole, WorkflowRole.workflow_id == Workflow.id)
        .where(Workflow.type == "tool")
        .where(Workflow.is_active.is_(True))
        .where(WorkflowRole.role_id.in_(role_ids))
        .distinct()
    )
    tools = result.scalars().all()

    return [
        {"id": str(t.id), "name": t.name, "description": t.tool_description or t.description}
        for t in tools
    ]
```

**Step 8: Add accessible-knowledge endpoint**

```python
@router.get("/accessible-knowledge")
async def get_accessible_knowledge(
    db: DbSession,
    user: CurrentActiveUser,
) -> list[dict]:
    """Get knowledge sources the current user can assign to their agents."""
    from src.models.orm.users import UserRole
    from src.models.orm.knowledge_sources import KnowledgeSource, KnowledgeSourceRole

    result = await db.execute(
        select(UserRole.role_id).where(UserRole.user_id == user.user_id)
    )
    role_ids = list(result.scalars().all())

    if not role_ids:
        return []

    result = await db.execute(
        select(KnowledgeSource)
        .join(KnowledgeSourceRole, KnowledgeSourceRole.knowledge_source_id == KnowledgeSource.id)
        .where(KnowledgeSource.is_active.is_(True))
        .where(KnowledgeSourceRole.role_id.in_(role_ids))
        .distinct()
    )
    sources = result.scalars().all()

    return [
        {"id": str(s.id), "name": s.name, "namespace": s.namespace, "description": s.description}
        for s in sources
    ]
```

**Step 9: Run tests**

Run: `./test.sh tests/unit/ -v -x`
Expected: All existing tests pass (some agent tests may need updating if they mock CurrentSuperuser)

**Step 10: Commit**

```bash
git add api/src/routers/agents.py
git commit -m "feat: loosen agent permissions for user creation, add promote + accessible endpoints"
```

---

## Task 8: Knowledge Source CRUD API

**Files:**
- Create: `api/src/routers/knowledge_sources.py`
- Modify: `api/src/routers/__init__.py`
- Modify: `api/src/main.py`

**Step 1: Create the knowledge sources router**

Create `api/src/routers/knowledge_sources.py` with CRUD for knowledge sources and documents within them. Follow the pattern from `api/src/routers/agents.py` and `api/src/routers/tables.py`.

Key endpoints:
- `GET /api/knowledge-sources` — List (any user, scoped)
- `POST /api/knowledge-sources` — Create (admin only)
- `GET /api/knowledge-sources/{id}` — Get (any user, access-checked)
- `PUT /api/knowledge-sources/{id}` — Update (admin only)
- `DELETE /api/knowledge-sources/{id}` — Soft delete (admin only)
- Role assignment: `GET/POST/DELETE /api/knowledge-sources/{id}/roles`
- Document CRUD: `GET/POST /api/knowledge-sources/{id}/documents`, `GET/PUT/DELETE /api/knowledge-sources/{id}/documents/{doc_id}`

Document create/update generates embeddings immediately using `get_embedding_client()` from `api/src/services/embeddings/factory.py` and stores via `KnowledgeRepository.store()` from `api/src/repositories/knowledge.py`.

This is a large file — implement it following the exact patterns from the agents router for CRUD, scoping, and role assignment.

**Step 2: Register the router**

In `api/src/routers/__init__.py`, add:
```python
from src.routers.knowledge_sources import router as knowledge_sources_router
```

Add `"knowledge_sources_router"` to `__all__`.

In `api/src/main.py`, add to imports and router registration:
```python
    knowledge_sources_router,
```
```python
    app.include_router(knowledge_sources_router)
```

**Step 3: Verify the API starts**

Run: `docker restart bifrost-dev-api-1 && sleep 5 && docker logs bifrost-dev-api-1 --tail 10`
Expected: API starts without errors

**Step 4: Commit**

```bash
git add api/src/routers/knowledge_sources.py api/src/routers/__init__.py api/src/main.py
git commit -m "feat: add knowledge sources CRUD API with document management and embedding"
```

---

## Task 9: Backend Tests

**Files:**
- Create: `api/tests/unit/routers/test_agents_user_created.py`
- Create: `api/tests/unit/repositories/test_org_scoped_private.py`

**Step 1: Write tests for private agent access control**

Test the key scenarios:
- Non-admin can create a private agent
- Non-admin cannot create an authenticated/role_based agent
- Non-admin can only edit/delete their own private agents
- Admin can see all private agents
- Promote works with correct permissions
- Promote denied without `can_promote_agent` permission
- `_can_access_entity` returns True for private agents owned by user
- `_can_access_entity` returns False for private agents not owned by user

**Step 2: Run tests to verify they fail**

Run: `./test.sh tests/unit/routers/test_agents_user_created.py -v`
Expected: FAIL (endpoints not yet matching test expectations if any mocking is off)

**Step 3: Fix any test issues**

**Step 4: Run full test suite**

Run: `./test.sh`
Expected: All tests pass

**Step 5: Commit**

```bash
git add api/tests/unit/
git commit -m "test: add tests for private agent creation, access control, promotion"
```

---

## Task 10: Frontend — Sidebar + Agents Page Changes

**Files:**
- Modify: `client/src/components/layout/Sidebar.tsx:86-98`
- Modify: `client/src/pages/Agents.tsx`
- Modify: `client/src/components/agents/AgentDialog.tsx`

**Step 1: Update sidebar**

In `client/src/components/layout/Sidebar.tsx`:

Remove `requiresPlatformAdmin` from the Agents nav item (so all users can access it).

Add Knowledge to the Data section:
```typescript
import { BookOpen } from "lucide-react";
```
Add after Tables item:
```typescript
{
    title: "Knowledge",
    href: "/knowledge",
    icon: BookOpen,
    requiresPlatformAdmin: true,
},
```

**Step 2: Update Agents page**

In `client/src/pages/Agents.tsx`:
- Remove the admin-only gate on the "Create Agent" button
- Add a "Private" badge (with Lock icon) next to private agents
- Show `owner_email` for admins on private agent cards
- Add "Promote" action button for owned private agents

**Step 3: Update AgentDialog**

In `client/src/components/agents/AgentDialog.tsx`:
- Add `"private"` access level option
- For non-admins: default to private, hide admin-only fields
- For non-admins: use `/api/agents/accessible-tools` and `/api/agents/accessible-knowledge` instead of the full tool/knowledge lists

**Step 4: Regenerate types**

Run: `cd /home/jack/GitHub/bifrost/client && npm run generate:types`

**Step 5: Verify frontend builds**

Run: `cd /home/jack/GitHub/bifrost/client && npm run tsc && npm run lint`
Expected: No errors

**Step 6: Commit**

```bash
git add client/src/components/layout/Sidebar.tsx client/src/pages/Agents.tsx client/src/components/agents/AgentDialog.tsx client/src/lib/v1.d.ts
git commit -m "feat: update sidebar and agents UI for private agents and knowledge nav"
```

---

## Task 11: Frontend — Knowledge Management Page

**Files:**
- Create: `client/src/pages/Knowledge.tsx`
- Create: `client/src/components/knowledge/KnowledgeSourceDialog.tsx`
- Create: `client/src/components/knowledge/KnowledgeDocumentList.tsx`
- Create: `client/src/components/knowledge/KnowledgeDocumentDrawer.tsx`

**Step 1: Create Knowledge page**

Create `client/src/pages/Knowledge.tsx` following the Tables page pattern:
- Header with title + create button
- Search box + org scope filter (admin)
- Table of knowledge sources: name, namespace, description, document count, scope badge
- Click a source to navigate to document list view
- Uses the new `/api/knowledge-sources` API

**Step 2: Create KnowledgeSourceDialog**

Create `client/src/components/knowledge/KnowledgeSourceDialog.tsx`:
- Dialog for creating/editing a knowledge source
- Fields: name, namespace (auto-generated), description, access level, role assignment

**Step 3: Create KnowledgeDocumentList**

Create `client/src/components/knowledge/KnowledgeDocumentList.tsx`:
- Lists documents within a knowledge source
- Table with: key, content preview, created_at, actions (view/edit/delete)
- Full-text search
- "Add Document" button

**Step 4: Create KnowledgeDocumentDrawer**

Create `client/src/components/knowledge/KnowledgeDocumentDrawer.tsx`:
- Sheet/drawer component for viewing/editing a document
- Uses the existing `TiptapEditor` from `client/src/components/ui/tiptap-editor.tsx`
- Read-only mode by default, "Edit" button toggles to editable
- Save triggers PUT to re-embed

**Step 5: Add routing**

Add `/knowledge` route to the app router, pointing to `Knowledge.tsx`.

**Step 6: Verify frontend builds**

Run: `cd /home/jack/GitHub/bifrost/client && npm run tsc && npm run lint`
Expected: No errors

**Step 7: Commit**

```bash
git add client/src/pages/Knowledge.tsx client/src/components/knowledge/
git commit -m "feat: add knowledge management page with tiptap document editor"
```

---

## Task 12: Role Management UI — Permissions

**Files:**
- Modify: Role edit dialog component (find exact path in `client/src/components/`)

**Step 1: Add permissions section to role edit dialog**

Add a "Permissions" section with toggles:
- `can_promote_agent` — "Allow users to promote private agents to the organization"

Wire to the `permissions` field on the role create/update API.

**Step 2: Verify**

Run: `cd /home/jack/GitHub/bifrost/client && npm run tsc && npm run lint`
Expected: No errors

**Step 3: Commit**

```bash
git add client/src/
git commit -m "feat: add permissions toggles to role management UI"
```

---

## Task 13: Final Verification

**Step 1: Backend checks**

Run: `cd /home/jack/GitHub/bifrost/api && pyright && ruff check .`
Expected: 0 errors

**Step 2: Frontend checks**

Run: `cd /home/jack/GitHub/bifrost/client && npm run tsc && npm run lint`
Expected: 0 errors

**Step 3: Full test suite**

Run: `./test.sh`
Expected: All tests pass

**Step 4: Manual testing**

- Apply migration: restart `bifrost-init` then API
- Log in as admin → create a knowledge source → add a document with tiptap
- Assign knowledge source to a role
- Assign a tool (workflow) to the same role
- Assign that role to a test user
- Log in as test user → create a private agent → see tools and knowledge from role
- As admin → see the private agent with owner info
- Give test user's role `can_promote_agent` permission
- As test user → promote the private agent
- Verify the agent is now org-scoped and owner is cleared
