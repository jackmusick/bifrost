# Fix Platform Admin Logic

## Status: PLANNING

## Problem Statement

The current `user_type` field is redundant and causes confusion:
- `user_type=PLATFORM` is always paired with `is_superuser=true`
- `user_type=ORG` is always paired with `is_superuser=false`
- The auth code incorrectly treats all PLATFORM users as having no organization

## Proposed Solution: Drop user_type Entirely

Use `is_superuser` + nullable `organization_id` as the source of truth.

### New Data Model

| is_superuser | organization_id | Meaning | Example |
|--------------|-----------------|---------|---------|
| true | UUID | Platform admin in an org | jack@company.com |
| false | UUID | Regular user in an org | user@company.com |
| true | NULL | System account (admin, global scope) | system@bifrost.local |
| false | NULL | ❌ **INVALID** - should error | - |

### Auth Logic (Simplified)

```python
org_id_str = payload.get("org_id")
is_superuser = payload.get("is_superuser", False)

if org_id_str:
    # User has an org - parse it
    organization_id = UUID(org_id_str)
elif is_superuser:
    # System/engine account - admin privileges, global scope
    organization_id = None
else:
    # Regular user without org - this is invalid/corrupted data
    logger.error(f"Invalid token: non-superuser without org_id")
    raise HTTPException(status_code=401, detail="Invalid token: missing organization")
```

### Scope Resolution (Unchanged)

The existing scope resolution in `workflow_execution.py` already works correctly:
- Global workflow → use caller's org_id (or GLOBAL if None)
- Org-scoped workflow → use workflow's org_id

With this fix:
- Platform admin (org_id=UUID) triggering global workflow → uses their org ✓
- System account (org_id=NULL) triggering global workflow → GLOBAL scope ✓

## Implementation Plan

### Phase 1: Database Migration

#### 1.1 Make organization_id nullable

```python
# alembic/versions/XXXXXXXX_nullable_org_id.py

def upgrade():
    # Allow NULL for organization_id
    op.alter_column('users', 'organization_id', nullable=True)

    # Add check constraint: org_id can only be NULL if is_superuser=true
    op.execute("""
        ALTER TABLE users ADD CONSTRAINT ck_users_org_requires_superuser
        CHECK (
            organization_id IS NOT NULL
            OR is_superuser = true
        )
    """)

def downgrade():
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_org_requires_superuser")
    # Note: Can't easily revert to NOT NULL without ensuring all rows have org_id
```

#### 1.2 Fix system user data

```python
def upgrade():
    # Set system user's org_id to NULL
    op.execute("""
        UPDATE users
        SET organization_id = NULL
        WHERE email = 'system@bifrost.local'
    """)
```

#### 1.3 Drop user_type column (can be done later or in same migration)

```python
def upgrade():
    # Drop the column - enum type will be orphaned but harmless
    op.drop_column('users', 'user_type')

def downgrade():
    # Would need to recreate column and repopulate based on is_superuser
    pass
```

### Phase 2: Update ORM Model

**File**: `api/src/models/orm/users.py`

```python
# REMOVE this:
user_type: Mapped[UserType] = mapped_column(...)

# CHANGE this:
organization_id: Mapped[UUID | None] = mapped_column(
    ForeignKey("organizations.id"), nullable=True  # Was nullable=False
)
```

### Phase 3: Fix Auth Code

**File**: `api/src/core/auth.py`

Replace the current token parsing logic:

```python
def extract_user_from_token(payload: dict[str, Any]) -> UserPrincipal | None:
    """Extract user principal from JWT payload."""
    user_id_str = payload.get("sub")
    if not user_id_str:
        return None

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        return None

    # Required claims
    if "email" not in payload:
        logger.warning(f"Token for user {user_id} missing email claim")
        return None

    is_superuser = payload.get("is_superuser", False)
    org_id_str = payload.get("org_id")

    # Parse organization_id
    organization_id: UUID | None = None
    if org_id_str:
        try:
            organization_id = UUID(org_id_str)
        except ValueError:
            logger.warning(f"Token has invalid org_id format: {org_id_str}")
            return None
    elif not is_superuser:
        # Non-superuser without org is invalid
        logger.error(
            f"Invalid token for user {user_id}: "
            "non-superuser must have organization_id"
        )
        return None
    # else: superuser with no org = system account (valid)

    return UserPrincipal(
        user_id=user_id,
        email=payload.get("email", ""),
        organization_id=organization_id,
        name=payload.get("name", ""),
        is_active=True,
        is_superuser=is_superuser,
        is_verified=True,
        roles=payload.get("roles", []),
    )
```

Apply same changes to WebSocket token parsing.

#### 3.1 Update UserPrincipal

**File**: `api/src/core/auth.py`

```python
@dataclass
class UserPrincipal:
    user_id: UUID
    email: str
    organization_id: UUID | None  # NULL for system accounts
    name: str = ""
    # REMOVE: user_type: str = "ORG"
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False
    roles: list[str] = field(default_factory=list)

    @property
    def is_platform_admin(self) -> bool:
        """Check if user is a platform admin."""
        return self.is_superuser  # Simplified!

    @property
    def is_system_account(self) -> bool:
        """Check if this is a system account (no org, has admin privileges)."""
        return self.is_superuser and self.organization_id is None
```

### Phase 4: Update Token Generation

**File**: `api/src/routers/auth.py`

Remove `user_type` from token claims:

```python
token_data = {
    "sub": str(user.id),
    "email": user.email,
    "name": user.name or user.email.split("@")[0],
    # REMOVE: "user_type": user.user_type.value,
    "is_superuser": user.is_superuser,
    "org_id": str(user.organization_id) if user.organization_id else None,
    "roles": roles,
}
```

### Phase 5: Update All user_type References

Search and replace all `user_type` references:

| Location | Current | New |
|----------|---------|-----|
| `auth.py:49` | `self.user_type == "PLATFORM"` | `self.is_superuser` |
| `auth.py:167` | `if user_type == "PLATFORM"` | Remove block |
| `users.py:66` | `UserORM.user_type != UserType.SYSTEM` | `UserORM.organization_id.isnot(None)` |
| `users.py:96` | `User.user_type != UserType.SYSTEM` | `User.organization_id.isnot(None)` |
| `contracts/users.py:44` | `user_type != UserType.PLATFORM` | `not is_superuser` |
| User provisioning | `UserType.PLATFORM/ORG` | Remove, set `is_superuser` only |

### Phase 6: Fix Tables SDK

**File**: `api/src/routers/tables.py`

Change read operations to not auto-create:

```python
# query_documents (line 625)
table = await get_table_or_404(ctx, name, scope)  # Was get_or_create_table

# count_documents (line 653)
table = await get_table_or_404(ctx, name, scope)  # Was get_or_create_table
```

### Phase 7: Update Frontend

After backend changes, regenerate types:
```bash
cd client && npm run generate:types
```

Then update frontend code that references `user_type`.

## Files to Modify

| File | Changes |
|------|---------|
| `api/alembic/versions/new.py` | Migration for nullable org_id, drop user_type |
| `api/src/models/orm/users.py` | Remove user_type, make org_id nullable |
| `api/src/models/enums.py` | Remove UserType enum (optional, can leave orphaned) |
| `api/src/core/auth.py` | Fix token parsing, update UserPrincipal |
| `api/src/routers/auth.py` | Remove user_type from token generation |
| `api/src/routers/users.py` | Update user filtering |
| `api/src/repositories/users.py` | Update user queries |
| `api/src/models/contracts/users.py` | Remove user_type validation |
| `api/src/services/user_provisioning.py` | Remove user_type assignment |
| `api/src/routers/tables.py` | Fix read operations |
| `client/src/**` | Update after type regeneration |

## Verification Checklist

- [ ] Migration runs successfully
- [ ] System user has organization_id=NULL, is_superuser=true
- [ ] Platform admin tokens work and include org_id
- [ ] Regular user tokens work and include org_id
- [ ] Token without org_id + is_superuser=false → error (401)
- [ ] Global workflow + platform admin → uses admin's org
- [ ] Global workflow + system user → GLOBAL scope
- [ ] tables.query() on non-existent table → 404
- [ ] tables.count() on non-existent table → 404
- [ ] User listings exclude system accounts (org_id IS NULL filter)
- [ ] All existing tests pass
- [ ] Type checking passes (pyright)
- [ ] Frontend works after type regeneration

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Existing tokens have user_type claim | Auth code ignores unknown claims - safe |
| PostgreSQL can't drop enum values | Drop column, leave enum orphaned - harmless |
| Frontend breaks | Regenerate types, update components |
| Old tokens without org_id | Will fail for non-superusers - correct behavior |

## Rollback Plan

If issues arise:
1. Revert migration (re-add user_type column)
2. Revert code changes
3. Deploy previous version

The migration is designed to be reversible except for the NOT NULL constraint on organization_id.
