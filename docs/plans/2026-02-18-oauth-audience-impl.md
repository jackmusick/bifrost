# OAuth Audience Field Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an optional `audience` field to OAuth provider configuration and simplify the connection dialog by removing preset tabs.

**Architecture:** Thread a new nullable `audience` string through the existing OAuth stack: ORM → Pydantic → service → router → scheduler → frontend. Separately, simplify the dialog UI by removing the preset/custom tabs wrapper.

**Tech Stack:** Python (SQLAlchemy, Pydantic, FastAPI), Alembic, TypeScript (React), shadcn/ui

---

### Task 1: Database migration — add `audience` column

**Files:**
- Create: `api/alembic/versions/20260218_add_oauth_audience.py`

**Step 1: Create the migration**

```bash
cd /home/jack/GitHub/bifrost/api && alembic revision -m "add_oauth_audience"
```

Then edit the generated file to contain:

```python
"""add_oauth_audience

Revision ID: <auto>
Revises: <auto>
Create Date: <auto>
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "<auto>"
down_revision = "<auto>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("oauth_providers", sa.Column("audience", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("oauth_providers", "audience")
```

**Step 2: Commit**

```bash
git add api/alembic/versions/20260218_add_oauth_audience.py
git commit -m "feat: add audience column to oauth_providers"
```

---

### Task 2: ORM model — add `audience` field

**Files:**
- Modify: `api/src/models/orm/oauth.py:36` (after `token_url` line)

**Step 1: Add the column**

Add after the `token_url` line (line 36):

```python
audience: Mapped[str | None] = mapped_column(String(500), default=None)
```

**Step 2: Commit**

```bash
git add api/src/models/orm/oauth.py
git commit -m "feat: add audience field to OAuthProvider ORM model"
```

---

### Task 3: Pydantic contracts — add `audience` to request/response models

**Files:**
- Modify: `api/src/models/contracts/oauth.py`

**Step 1: Add `audience` to `CreateOAuthConnectionRequest`**

After the `scopes` field (line 67), add:

```python
audience: str | None = Field(
    None,
    max_length=500,
    description="OAuth audience parameter - identifies the target API/resource for the token request (e.g., required by Pax8, Auth0)"
)
```

**Step 2: Add `audience` to `UpdateOAuthConnectionRequest`**

After the `scopes` field (line 116), add:

```python
audience: str | None = Field(
    default=None,
    max_length=500,
    description="OAuth audience parameter"
)
```

**Step 3: Add `audience` to `OAuthConnectionDetail`**

After the `scopes` field (line 186), add:

```python
audience: str | None = Field(
    default=None,
    description="OAuth audience parameter for token requests"
)
```

**Step 4: Commit**

```bash
git add api/src/models/contracts/oauth.py
git commit -m "feat: add audience field to OAuth Pydantic contracts"
```

---

### Task 4: OAuth provider client — accept and send `audience` in token requests

**Files:**
- Modify: `api/src/services/oauth_provider.py`

**Step 1: Update `exchange_code_for_token` signature and payload**

Add `audience: str | None = None` parameter after `redirect_uri`. Add to payload:

```python
if audience:
    payload["audience"] = audience
```

**Step 2: Update `refresh_access_token` signature and payload**

Add `audience: str | None = None` parameter after `client_secret`. Add to payload:

```python
if audience:
    payload["audience"] = audience
```

**Step 3: Update `get_client_credentials_token` signature and payload**

Add `audience: str | None = None` parameter after `scopes`. Add to payload:

```python
if audience:
    payload["audience"] = audience
```

**Step 4: Commit**

```bash
git add api/src/services/oauth_provider.py
git commit -m "feat: pass audience parameter in OAuth token requests"
```

---

### Task 5: Router — thread `audience` through create, update, callback, and refresh

**Files:**
- Modify: `api/src/routers/oauth_connections.py`

**Step 1: `create_connection` endpoint (line 528)**

When constructing the `OAuthProvider` object, add `audience=request.audience` after the `scopes` line.

**Step 2: `update_connection` repository method (after line 252)**

Add to the `update_connection` method in `OAuthConnectionRepository`:

```python
if request.audience is not None:
    provider.audience = request.audience
```

**Step 3: `_to_detail` method (line 410)**

Add `audience=provider.audience,` to the `OAuthConnectionDetail(...)` constructor.

**Step 4: `oauth_callback` endpoint (line 958)**

Pass `audience=provider.audience` to `oauth_client.exchange_code_for_token()`.

**Step 5: `refresh_token` endpoint — client_credentials path (line 793)**

Pass `audience=provider.audience` to `oauth_client.get_client_credentials_token()`.

**Step 6: `refresh_token` endpoint — authorization_code path**

Find the call to `oauth_client.refresh_access_token()` in the else branch and pass `audience=provider.audience`.

**Step 7: Commit**

```bash
git add api/src/routers/oauth_connections.py
git commit -m "feat: thread audience through OAuth router endpoints"
```

---

### Task 6: Scheduler — pass `audience` during token refresh

**Files:**
- Modify: `api/src/jobs/schedulers/oauth_token_refresh.py:220`

**Step 1: Pass audience to refresh call**

In `_refresh_single_token`, update the `oauth_client.refresh_access_token()` call (around line 220) to include `audience=provider.audience`.

**Step 2: Commit**

```bash
git add api/src/jobs/schedulers/oauth_token_refresh.py
git commit -m "feat: pass audience in scheduled OAuth token refresh"
```

---

### Task 7: Frontend — add audience field and remove preset tabs

**Files:**
- Modify: `client/src/components/oauth/CreateOAuthConnectionDialog.tsx`

**Step 1: Add `audience` to form state**

In `initialFormData` (line 63), add `audience: ""` to the default object, and `audience: existingConnection.audience || ""` to the edit mode object.

NOTE: The `audience` field will be available on the generated types after `npm run generate:types`. If the type doesn't include `audience` yet, add it manually to the form state as a separate state variable or cast as needed.

**Step 2: Remove the Tabs wrapper and preset selector**

Remove the entire `<Tabs>` component (lines ~229-316), including:
- The `TabsList` with "Quick Start (Presets)" and "Custom Provider" triggers
- The `TabsContent value="preset"` section (preset selector dropdown and docs link)
- The `TabsContent value="custom"` section (custom provider alert)
- The `mode` state variable and `selectedPreset` state variable
- The `handlePresetSelect` function
- The `Tabs`, `TabsContent`, `TabsList`, `TabsTrigger` imports
- The `Sparkles` icon import (only used by preset tab)

Keep the redirect URI alert that comes before the tabs.

**Step 3: Add audience input field**

After the Token URL field and before the Scopes field, add:

```tsx
<div className="space-y-2">
    <Label htmlFor="audience">
        Audience
    </Label>
    <Input
        id="audience"
        value={formData.audience || ""}
        onChange={(e) =>
            setFormData({
                ...formData,
                audience: e.target.value,
            })
        }
        placeholder="https://api.example.com"
        className="font-mono text-xs"
    />
    <p className="text-xs text-muted-foreground">
        Target API identifier sent with token
        requests. Required by some providers
        (e.g., Pax8, Auth0).
    </p>
</div>
```

**Step 4: Add `audience` to the update payload in `handleSubmit`**

In the `updateData` object, add `audience: formData.audience || null`.

**Step 5: Commit**

```bash
git add client/src/components/oauth/CreateOAuthConnectionDialog.tsx
git commit -m "feat: add audience field and remove preset tabs from OAuth dialog"
```

---

### Task 8: Regenerate types and verify

**Step 1: Restart bifrost-init to apply migration, then restart API**

```bash
docker restart bifrost-init
# Wait a few seconds for migration
docker restart bifrost-dev-api-1
```

**Step 2: Regenerate TypeScript types**

```bash
cd /home/jack/GitHub/bifrost/client && npm run generate:types
```

**Step 3: Run backend checks**

```bash
cd /home/jack/GitHub/bifrost/api && pyright
cd /home/jack/GitHub/bifrost/api && ruff check .
```

**Step 4: Run frontend checks**

```bash
cd /home/jack/GitHub/bifrost/client && npm run tsc
cd /home/jack/GitHub/bifrost/client && npm run lint
```

**Step 5: Run tests**

```bash
cd /home/jack/GitHub/bifrost && ./test.sh
```

**Step 6: Final commit if any type fixups needed**

```bash
git add -A && git commit -m "chore: regenerate types and fix any type issues"
```
