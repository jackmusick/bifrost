# Form Embed Auth Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable HMAC-authenticated iframe embedding for Bifrost forms, with HMAC params automatically merged into workflow input.

**Architecture:** Mirrors the existing app embed system. New `form_embed_secrets` table, new embed entry route, middleware allowlist expansion, and frontend embed detection on the RunForm page. Reuses `verify_embed_hmac`, `UserPrincipal.embed`, and `EmbedUser` role infrastructure.

**Tech Stack:** Python/FastAPI (backend), SQLAlchemy ORM, Alembic migrations, React/TypeScript (frontend)

---

### Task 1: ORM Model — `FormEmbedSecret`

**Files:**
- Create: `api/src/models/orm/form_embed_secrets.py`
- Modify: `api/src/models/orm/__init__.py`
- Modify: `api/src/models/orm/forms.py` (add relationship)

**Step 1: Create the ORM model**

Create `api/src/models/orm/form_embed_secrets.py`:

```python
"""ORM model for form embed secrets."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.orm.base import Base


class FormEmbedSecret(Base):
    """Shared secret for HMAC-authenticated iframe embedding of forms."""

    __tablename__ = "form_embed_secrets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    form_id: Mapped[UUID] = mapped_column(
        ForeignKey("forms.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )

    form = relationship("Form", back_populates="embed_secrets")

    __table_args__ = (
        Index("ix_form_embed_secrets_form_id", "form_id"),
    )
```

**Step 2: Add relationship to Form model**

In `api/src/models/orm/forms.py`, add to the `Form` class relationships section (after `fields`):

```python
embed_secrets: Mapped[list["FormEmbedSecret"]] = relationship(
    "FormEmbedSecret", back_populates="form", cascade="all, delete-orphan", passive_deletes=True
)
```

Add the TYPE_CHECKING import at the top of the file:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.orm.form_embed_secrets import FormEmbedSecret
```

**Step 3: Register in `__init__.py`**

In `api/src/models/orm/__init__.py`:
- Add import: `from src.models.orm.form_embed_secrets import FormEmbedSecret`
- Add to `__all__`: `"FormEmbedSecret"`

**Step 4: Commit**

```
feat: add FormEmbedSecret ORM model
```

---

### Task 2: Alembic Migration

**Files:**
- Create: `api/alembic/versions/20260217_add_form_embed_secrets.py`

**Step 1: Create migration file**

```python
"""add form_embed_secrets table

Revision ID: 20260217_form_embed_secrets
Revises: 20260216_embed_secrets
Create Date: 2026-02-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260217_form_embed_secrets"
down_revision = "20260216_embed_secrets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "form_embed_secrets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "form_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("forms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_form_embed_secrets_form_id",
        "form_embed_secrets",
        ["form_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_form_embed_secrets_form_id")
    op.drop_table("form_embed_secrets")
```

**Step 2: Commit**

```
feat: add form_embed_secrets migration
```

---

### Task 3: Pydantic Contracts for Form Embed Secrets

**Files:**
- Modify: `api/src/models/contracts/forms.py`

The embed secret contract models (`EmbedSecretCreate`, `EmbedSecretResponse`, `EmbedSecretCreatedResponse`, `EmbedSecretUpdate`) already exist in `api/src/models/contracts/applications.py` and are generic enough to reuse directly. No new models needed — we import them in the router.

**Step 1: Verify reuse works**

Check that `EmbedSecretCreate`, `EmbedSecretResponse`, `EmbedSecretCreatedResponse`, `EmbedSecretUpdate` in `api/src/models/contracts/applications.py` have no app-specific fields. They don't — they're generic (name, secret, is_active, created_at, raw_secret). We'll import them in the next task.

**Step 2: Commit** (skip if no changes)

---

### Task 4: Form Embed Secrets CRUD Router

**Files:**
- Create: `api/src/routers/form_embed_secrets.py`
- Modify: `api/src/routers/__init__.py`
- Modify: `api/src/main.py`

**Step 1: Write the E2E test**

Create `api/tests/e2e/api/test_form_embed_secrets.py`:

```python
"""E2E tests for form embed secret CRUD."""

import pytest


def _create_form(client, headers):
    """Create a minimal form for testing."""
    r = client.post("/api/forms", headers=headers, json={
        "name": "Embed Secret Test Form",
        "description": "Test form for embed secrets",
    })
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.e2e
class TestFormEmbedSecrets:
    @pytest.fixture
    def test_form(self, e2e_client, platform_admin):
        form = _create_form(e2e_client, platform_admin.headers)
        yield form

    def test_create_embed_secret_autogenerated(self, e2e_client, platform_admin, test_form):
        """Creating a secret without providing one should auto-generate it."""
        r = e2e_client.post(
            f"/api/forms/{test_form['id']}/embed-secrets",
            headers=platform_admin.headers,
            json={"name": "Test Secret"},
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert "raw_secret" in data
        assert len(data["raw_secret"]) > 20
        assert data["name"] == "Test Secret"
        assert data["is_active"] is True

    def test_create_embed_secret_user_provided(self, e2e_client, platform_admin, test_form):
        """Creating a secret with a user-provided value should store and return it."""
        provided = "my-halo-secret-abc123"
        r = e2e_client.post(
            f"/api/forms/{test_form['id']}/embed-secrets",
            headers=platform_admin.headers,
            json={"name": "Halo Prod", "secret": provided},
        )
        assert r.status_code == 201, r.text
        assert r.json()["raw_secret"] == provided

    def test_list_embed_secrets_hides_raw(self, e2e_client, platform_admin, test_form):
        """Listing secrets should NOT return the raw secret value."""
        e2e_client.post(
            f"/api/forms/{test_form['id']}/embed-secrets",
            headers=platform_admin.headers,
            json={"name": "Listed Secret"},
        )
        r = e2e_client.get(
            f"/api/forms/{test_form['id']}/embed-secrets",
            headers=platform_admin.headers,
        )
        assert r.status_code == 200, r.text
        secrets_list = r.json()
        assert len(secrets_list) >= 1
        for s in secrets_list:
            assert "raw_secret" not in s
            assert "secret_encrypted" not in s

    def test_deactivate_embed_secret(self, e2e_client, platform_admin, test_form):
        """Should be able to deactivate an embed secret."""
        create_r = e2e_client.post(
            f"/api/forms/{test_form['id']}/embed-secrets",
            headers=platform_admin.headers,
            json={"name": "To Deactivate"},
        )
        secret_id = create_r.json()["id"]
        r = e2e_client.patch(
            f"/api/forms/{test_form['id']}/embed-secrets/{secret_id}",
            headers=platform_admin.headers,
            json={"is_active": False},
        )
        assert r.status_code == 200, r.text
        assert r.json()["is_active"] is False

    def test_delete_embed_secret(self, e2e_client, platform_admin, test_form):
        """Should be able to delete an embed secret."""
        create_r = e2e_client.post(
            f"/api/forms/{test_form['id']}/embed-secrets",
            headers=platform_admin.headers,
            json={"name": "To Delete"},
        )
        secret_id = create_r.json()["id"]
        r = e2e_client.delete(
            f"/api/forms/{test_form['id']}/embed-secrets/{secret_id}",
            headers=platform_admin.headers,
        )
        assert r.status_code == 204, r.text

    def test_non_admin_cannot_manage_secrets(self, e2e_client, org1_user, test_form):
        """Regular org users should NOT be able to manage embed secrets."""
        r = e2e_client.post(
            f"/api/forms/{test_form['id']}/embed-secrets",
            headers=org1_user.headers,
            json={"name": "Unauthorized"},
        )
        assert r.status_code == 403, r.text
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/e2e/api/test_form_embed_secrets.py -v`
Expected: FAIL — 404 because the endpoint doesn't exist yet.

**Step 3: Create the router**

Create `api/src/routers/form_embed_secrets.py`:

```python
"""CRUD endpoints for form embed secrets."""

import logging
import secrets
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, status
from sqlalchemy import select

from src.core.auth import Context, CurrentSuperuser
from src.core.security import encrypt_secret
from src.models.contracts.applications import (
    EmbedSecretCreate,
    EmbedSecretCreatedResponse,
    EmbedSecretResponse,
    EmbedSecretUpdate,
)
from src.models.orm.form_embed_secrets import FormEmbedSecret
from src.models.orm.forms import Form

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/forms/{form_id}/embed-secrets",
    tags=["Form Embed Secrets"],
)


async def _get_form_or_404(ctx: Context, form_id: UUID) -> Form:
    result = await ctx.db.execute(select(Form).where(Form.id == form_id))
    form = result.scalar_one_or_none()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    return form


@router.post(
    "",
    response_model=EmbedSecretCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an embed secret for a form",
)
async def create_form_embed_secret(
    body: EmbedSecretCreate,
    ctx: Context,
    current_user: CurrentSuperuser,
    form_id: UUID = Path(...),
):
    await _get_form_or_404(ctx, form_id)

    raw_secret = body.secret or secrets.token_urlsafe(32)
    encrypted = encrypt_secret(raw_secret)

    record = FormEmbedSecret(
        form_id=form_id,
        name=body.name,
        secret_encrypted=encrypted,
        created_by=current_user.user_id,
    )
    ctx.db.add(record)
    await ctx.db.commit()
    await ctx.db.refresh(record)

    return EmbedSecretCreatedResponse(
        id=str(record.id),
        name=record.name,
        is_active=record.is_active,
        created_at=record.created_at,
        raw_secret=raw_secret,
    )


@router.get(
    "",
    response_model=list[EmbedSecretResponse],
    summary="List embed secrets for a form",
)
async def list_form_embed_secrets(
    ctx: Context,
    _user: CurrentSuperuser,
    form_id: UUID = Path(...),
):
    await _get_form_or_404(ctx, form_id)

    result = await ctx.db.execute(
        select(FormEmbedSecret)
        .where(FormEmbedSecret.form_id == form_id)
        .order_by(FormEmbedSecret.created_at.desc())
    )
    records = result.scalars().all()

    return [
        EmbedSecretResponse(
            id=str(r.id),
            name=r.name,
            is_active=r.is_active,
            created_at=r.created_at,
        )
        for r in records
    ]


@router.patch(
    "/{secret_id}",
    response_model=EmbedSecretResponse,
    summary="Update a form embed secret",
)
async def update_form_embed_secret(
    body: EmbedSecretUpdate,
    ctx: Context,
    _user: CurrentSuperuser,
    form_id: UUID = Path(...),
    secret_id: UUID = Path(...),
):
    result = await ctx.db.execute(
        select(FormEmbedSecret).where(
            FormEmbedSecret.id == secret_id,
            FormEmbedSecret.form_id == form_id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Embed secret not found")

    if body.is_active is not None:
        record.is_active = body.is_active
    if body.name is not None:
        record.name = body.name

    await ctx.db.commit()
    await ctx.db.refresh(record)

    return EmbedSecretResponse(
        id=str(record.id),
        name=record.name,
        is_active=record.is_active,
        created_at=record.created_at,
    )


@router.delete(
    "/{secret_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a form embed secret",
)
async def delete_form_embed_secret(
    ctx: Context,
    _user: CurrentSuperuser,
    form_id: UUID = Path(...),
    secret_id: UUID = Path(...),
):
    result = await ctx.db.execute(
        select(FormEmbedSecret).where(
            FormEmbedSecret.id == secret_id,
            FormEmbedSecret.form_id == form_id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Embed secret not found")

    await ctx.db.delete(record)
    await ctx.db.commit()
```

**Step 4: Register the router**

In `api/src/routers/__init__.py`, add:
```python
from src.routers.form_embed_secrets import router as form_embed_secrets_router
```
Add `"form_embed_secrets_router"` to `__all__`.

In `api/src/main.py`, add import and `app.include_router(form_embed_secrets_router)` near the other embed router registrations.

**Step 5: Run tests**

Run: `./test.sh tests/e2e/api/test_form_embed_secrets.py -v`
Expected: All PASS.

**Step 6: Commit**

```
feat: add form embed secrets CRUD endpoints
```

---

### Task 5: UserPrincipal — Add `form_id` and `verified_params`

**Files:**
- Modify: `api/src/core/auth.py`

**Step 1: Add fields to UserPrincipal**

In `api/src/core/auth.py`, add to the `UserPrincipal` dataclass (after `app_id`):

```python
form_id: str | None = None  # Form ID for form embed tokens
verified_params: dict[str, str] | None = None  # HMAC-verified query params
```

**Step 2: Parse from JWT**

In `get_current_user_optional` where the `UserPrincipal` is constructed (around line 201), add:

```python
form_id=payload.get("form_id"),
verified_params=payload.get("verified_params"),
```

Do the same in `get_current_user_ws` (around line 449).

**Step 3: Commit**

```
feat: add form_id and verified_params to UserPrincipal
```

---

### Task 6: Embed Entry Route — `/embed/forms/{form_id}`

**Files:**
- Modify: `api/src/routers/embed.py`

**Step 1: Write the E2E test**

Add to `api/tests/e2e/api/test_form_embed_secrets.py` (or new file `api/tests/e2e/api/test_form_embed.py`):

```python
"""E2E tests for form embed HMAC flow."""

import hashlib
import hmac as hmac_module

import pytest


def _compute_hmac(params: dict, secret: str) -> str:
    message = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac_module.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


@pytest.mark.e2e
class TestFormEmbed:
    @pytest.fixture
    def form_with_secret(self, e2e_client, platform_admin):
        """Create a form with an embed secret."""
        # Create form
        r = e2e_client.post("/api/forms", headers=platform_admin.headers, json={
            "name": "Embed Test Form",
        })
        assert r.status_code == 201, r.text
        form = r.json()

        # Create embed secret
        r = e2e_client.post(
            f"/api/forms/{form['id']}/embed-secrets",
            headers=platform_admin.headers,
            json={"name": "Test", "secret": "test-secret-123"},
        )
        assert r.status_code == 201, r.text

        yield {"form": form, "secret": "test-secret-123"}

    def test_embed_form_valid_hmac(self, e2e_client, form_with_secret):
        """Valid HMAC should redirect with embed token in fragment."""
        form_id = form_with_secret["form"]["id"]
        params = {"agent_id": "42", "ticket_id": "1001"}
        hmac_sig = _compute_hmac(params, form_with_secret["secret"])

        r = e2e_client.get(
            f"/embed/forms/{form_id}",
            params={**params, "hmac": hmac_sig},
            follow_redirects=False,
        )
        assert r.status_code == 302
        location = r.headers["location"]
        assert location.startswith(f"/execute/{form_id}#embed_token=")

    def test_embed_form_invalid_hmac(self, e2e_client, form_with_secret):
        """Invalid HMAC should return 403."""
        form_id = form_with_secret["form"]["id"]
        r = e2e_client.get(
            f"/embed/forms/{form_id}",
            params={"agent_id": "42", "hmac": "invalid"},
        )
        assert r.status_code == 403

    def test_embed_form_missing_hmac(self, e2e_client, form_with_secret):
        """Missing HMAC param should return 403."""
        form_id = form_with_secret["form"]["id"]
        r = e2e_client.get(
            f"/embed/forms/{form_id}",
            params={"agent_id": "42"},
        )
        assert r.status_code == 403

    def test_embed_form_nonexistent(self, e2e_client):
        """Non-existent form should return 404."""
        import uuid
        r = e2e_client.get(
            f"/embed/forms/{uuid.uuid4()}",
            params={"hmac": "anything"},
        )
        assert r.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/e2e/api/test_form_embed.py -v`
Expected: FAIL — 404 because route doesn't exist.

**Step 3: Add form embed route**

In `api/src/routers/embed.py`, add a new endpoint after the existing `embed_app`:

```python
from src.models.orm.forms import Form as FormORM
from src.models.orm.form_embed_secrets import FormEmbedSecret


@router.get("/forms/{form_id}")
async def embed_form(
    request: Request,
    form_id: str = Path(...),
):
    """Public entry point for HMAC-authenticated form iframe embedding."""
    from uuid import UUID as PyUUID

    query_params = dict(request.query_params)

    if "hmac" not in query_params:
        raise HTTPException(status_code=403, detail="Missing HMAC signature")

    # Parse form_id as UUID
    try:
        form_uuid = PyUUID(form_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Form not found")

    # Look up the form and its active embed secrets
    async with get_db_context() as db:
        result = await db.execute(
            select(FormORM)
            .where(FormORM.id == form_uuid)
            .options(selectinload(FormORM.embed_secrets))
        )
        form = result.scalar_one_or_none()

    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    active_secrets = [s for s in form.embed_secrets if s.is_active]
    if not active_secrets:
        raise HTTPException(status_code=403, detail="No embed secrets configured")

    # Try each active secret
    verified = False
    for secret_record in active_secrets:
        raw_secret = decrypt_secret(secret_record.secret_encrypted)
        if verify_embed_hmac(query_params, raw_secret):
            verified = True
            break

    if not verified:
        raise HTTPException(status_code=403, detail="Invalid HMAC signature")

    # Extract verified params (everything except hmac)
    verified_params = {k: v for k, v in query_params.items() if k != "hmac"}

    # Issue a scoped embed access token
    token_data = {
        "sub": SYSTEM_USER_ID,
        "form_id": str(form.id),
        "org_id": str(form.organization_id) if form.organization_id else None,
        "verified_params": verified_params,
        "email": "embed@internal.gobifrost.com",
        "is_superuser": False,
        "embed": True,
        "roles": ["EmbedUser"],
    }
    access_token = create_access_token(token_data, expires_delta=timedelta(hours=8))

    redirect = RedirectResponse(
        url=f"/execute/{form.id}#embed_token={access_token}",
        status_code=302,
    )

    # Set permissive framing headers for embed route
    redirect.headers["Content-Security-Policy"] = "frame-ancestors *"
    redirect.headers["X-Frame-Options"] = "ALLOWALL"

    return redirect
```

Add `selectinload` to the imports at the top if not already imported. Also add the new model imports.

**Step 4: Run tests**

Run: `./test.sh tests/e2e/api/test_form_embed.py -v`
Expected: All PASS.

**Step 5: Commit**

```
feat: add /embed/forms/{form_id} HMAC entry point
```

---

### Task 7: Middleware — Allowlist Form Endpoints

**Files:**
- Modify: `api/src/core/embed_middleware.py`

**Step 1: Add form patterns**

In `api/src/core/embed_middleware.py`, add to `EMBED_ALLOWED_PATTERNS`:

```python
# Form loading and execution
r"^/api/forms/[^/]+$",              # GET /api/forms/{form_id}
r"^/api/forms/[^/]+/execute$",      # POST /api/forms/{form_id}/execute
r"^/api/forms/[^/]+/startup$",      # POST /api/forms/{form_id}/startup
r"^/api/forms/[^/]+/upload$",       # POST /api/forms/{form_id}/upload
```

**Step 2: Commit**

```
feat: add form endpoints to embed middleware allowlist
```

---

### Task 8: Merge `verified_params` into Form Execution

**Files:**
- Modify: `api/src/routers/forms.py`

**Step 1: Write the test**

Add to `api/tests/e2e/api/test_form_embed.py`:

```python
def test_embed_verified_params_merged_into_execution(self, e2e_client, form_with_secret):
    """Verified params from HMAC should be merged into workflow input."""
    form_id = form_with_secret["form"]["id"]
    params = {"agent_id": "42"}
    hmac_sig = _compute_hmac(params, form_with_secret["secret"])

    # Get the embed token via the redirect
    r = e2e_client.get(
        f"/embed/forms/{form_id}",
        params={**params, "hmac": hmac_sig},
        follow_redirects=False,
    )
    assert r.status_code == 302
    location = r.headers["location"]
    embed_token = location.split("#embed_token=")[1]

    # Use the embed token to call the form endpoint
    embed_headers = {"Authorization": f"Bearer {embed_token}"}

    # Verify the form is accessible with embed token
    r = e2e_client.get(f"/api/forms/{form_id}", headers=embed_headers)
    assert r.status_code == 200
```

Note: A full execution test requires a workflow to exist. The unit test above validates the token works for form access. The actual param merging is tested by checking the code path in the next step.

**Step 2: Modify `execute_form`**

In `api/src/routers/forms.py`, in the `execute_form` function, change the merge line (around line 727):

From:
```python
merged_params = {**(form.default_launch_params or {}), **request.form_data}
```

To:
```python
# Merge: defaults < verified HMAC params < user form input
verified_params = getattr(ctx.user, 'verified_params', None) or {}
merged_params = {**(form.default_launch_params or {}), **verified_params, **request.form_data}
```

Also update `_check_form_access` to allow embed users. Add at the beginning of the function (after the superuser check):

```python
# Embed users with matching form_id have access
if hasattr(ctx_user, 'embed') if False else False:
    pass
```

Actually, simpler: embed tokens use SYSTEM_USER_ID which is a superuser, so the `is_superuser` check already passes. BUT — the embed token sets `is_superuser: False`. So we need to add embed access.

In `_check_form_access`, after the superuser check:

```python
# Embed users bypass access control (already verified via HMAC)
if getattr(user_principal, 'embed', False):
    return True
```

Wait — `_check_form_access` takes raw fields, not a UserPrincipal. We need to thread the embed flag through. The cleanest approach: check `ctx.user.embed` in `execute_form` before calling `_check_form_access`.

In `execute_form`, replace the access check block:

```python
# Check access — embed users are pre-authorized via HMAC
if not ctx.user.embed:
    has_access = await _check_form_access(db, form, ctx.user.user_id, ctx.org_id, ctx.user.is_superuser)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this form",
        )
```

Do the same for `execute_startup_workflow` and the file upload endpoint.

**Step 3: Also merge verified_params into startup workflow**

In `execute_startup_workflow`, change:

```python
merged_params = {**(form.default_launch_params or {}), **input_data}
```

To:

```python
verified_params = getattr(ctx.user, 'verified_params', None) or {}
merged_params = {**(form.default_launch_params or {}), **verified_params, **input_data}
```

**Step 4: Run tests**

Run: `./test.sh tests/e2e/api/test_form_embed.py -v`
Expected: All PASS.

**Step 5: Commit**

```
feat: merge verified_params into form execution and bypass access check for embed
```

---

### Task 9: Frontend — Embed Mode for RunForm

**Files:**
- Modify: `client/src/pages/RunForm.tsx`

**Step 1: Update RunForm to detect embed mode and hide nav**

```typescript
import { useAuth } from "@/contexts/AuthContext";

// Inside RunForm component, add:
const { hasRole } = useAuth();  // already imported, just add hasRole
const isEmbed = hasRole("EmbedUser");
```

When embed:
- Hide the back button and header chrome
- Pass `preventNavigation={true}` to FormRenderer
- Simplify to just the form with title

Replace the return block to conditionally render:

```typescript
if (isEmbed) {
    return (
        <div className="p-6 max-w-2xl mx-auto space-y-6">
            <div className="text-center">
                <h1 className="text-4xl font-extrabold tracking-tight">
                    {form.name}
                </h1>
                {form.description && (
                    <p className="mt-2 text-muted-foreground">
                        {form.description}
                    </p>
                )}
            </div>
            <FormRenderer
                form={form}
                preventNavigation
            />
        </div>
    );
}

// ... existing non-embed return
```

**Step 2: Commit**

```
feat: add embed mode to RunForm page - hide nav, prevent navigation
```

---

### Task 10: Verification & Cleanup

**Step 1: Run full backend checks**

```bash
cd api && pyright
cd api && ruff check .
```

**Step 2: Regenerate frontend types**

```bash
cd client && npm run generate:types
```

**Step 3: Frontend checks**

```bash
cd client && npm run tsc
cd client && npm run lint
```

**Step 4: Run all tests**

```bash
./test.sh
```

**Step 5: Final commit if any fixes needed**

```
chore: fix lint/type issues from form embed implementation
```
