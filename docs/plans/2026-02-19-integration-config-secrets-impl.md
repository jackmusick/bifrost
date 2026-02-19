# Integration Config Secrets Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix `_save_config()` in the integrations router to properly set `config_type` and encrypt secret values, add integration name to the Config list page, and backfill existing data.

**Architecture:** The Config router (`config.py`) already correctly handles `config_type` and encryption. The integrations router (`integrations.py`) bypasses this by creating `ConfigModel` entries without setting `config_type` or encrypting. We fix `_save_config()` to mirror the Config router's behavior, fix read paths to decrypt, add integration info to `ConfigResponse`, and add an E2E test covering the full round-trip.

**Tech Stack:** Python/FastAPI (backend), TypeScript/React (frontend), Alembic (migration), Fernet encryption (`encrypt_secret`/`decrypt_secret`)

---

### Task 1: Fix `_save_config()` to set `config_type` and encrypt secrets

**Files:**
- Modify: `api/src/routers/integrations.py:369-451` (the `_save_config` method)

**Step 1: Write the failing E2E test**

Add a new test class to `api/tests/e2e/api/test_integrations.py` that verifies secret config values are encrypted and masked.

```python
# Add at the end of the file, before any final comments

@pytest.mark.e2e
class TestIntegrationConfigSecrets:
    """Test that integration config secrets are properly encrypted and typed."""

    @pytest.fixture
    def integration_with_secret_schema(self, e2e_client, platform_admin):
        """Create an integration with a secret config field."""
        integration_name = f"e2e_secret_test_{uuid4().hex[:8]}"
        response = e2e_client.post(
            "/api/integrations",
            headers=platform_admin.headers,
            json={
                "name": integration_name,
                "config_schema": [
                    {"key": "base_url", "type": "string", "required": True},
                    {"key": "api_key", "type": "secret", "required": True},
                ],
            },
        )
        assert response.status_code == 201
        integration = response.json()

        yield integration

        # Cleanup
        e2e_client.delete(
            f"/api/integrations/{integration['id']}",
            headers=platform_admin.headers,
        )

    def test_secret_defaults_are_encrypted_in_db(
        self, e2e_client, platform_admin, integration_with_secret_schema
    ):
        """Secret config values saved via integration defaults are encrypted."""
        integration = integration_with_secret_schema

        # Set defaults including a secret
        response = e2e_client.put(
            f"/api/integrations/{integration['id']}/config",
            headers=platform_admin.headers,
            json={
                "config": {
                    "base_url": "https://api.example.com",
                    "api_key": "super-secret-key-12345",
                }
            },
        )
        assert response.status_code == 200

        # Verify the config list endpoint masks the secret
        response = e2e_client.get(
            "/api/config",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        configs = response.json()

        # Find our api_key config
        api_key_config = next(
            (c for c in configs if c["key"] == "api_key"
             and c.get("integration_id") == integration["id"]),
            None,
        )
        assert api_key_config is not None, f"api_key config not found in {[c['key'] for c in configs]}"
        assert api_key_config["type"] == "secret", f"Expected type 'secret', got '{api_key_config['type']}'"
        assert api_key_config["value"] == "[SECRET]", f"Secret value should be masked, got '{api_key_config['value']}'"

        # Verify the SDK endpoint returns the DECRYPTED value
        # (we need a mapping for this)

    def test_secret_roundtrip_via_sdk(
        self, e2e_client, platform_admin, integration_with_secret_schema, org1
    ):
        """Secret saved via integration defaults can be decrypted for SDK consumption."""
        integration = integration_with_secret_schema

        # Set defaults including a secret
        e2e_client.put(
            f"/api/integrations/{integration['id']}/config",
            headers=platform_admin.headers,
            json={
                "config": {
                    "base_url": "https://api.example.com",
                    "api_key": "my-secret-api-key",
                }
            },
        )

        # Create mapping
        response = e2e_client.post(
            f"/api/integrations/{integration['id']}/mappings",
            headers=platform_admin.headers,
            json={
                "organization_id": str(org1["id"]),
                "entity_id": "secret-roundtrip-test",
            },
        )
        assert response.status_code == 201
        mapping = response.json()

        try:
            # Get SDK data - should return decrypted secret
            response = e2e_client.get(
                f"/api/integrations/sdk/{integration['name']}",
                headers=platform_admin.headers,
                params={"org_id": str(org1["id"])},
            )
            assert response.status_code == 200
            data = response.json()

            assert data["config"]["base_url"] == "https://api.example.com"
            assert data["config"]["api_key"] == "my-secret-api-key"
        finally:
            e2e_client.delete(
                f"/api/integrations/{integration['id']}/mappings/{mapping['id']}",
                headers=platform_admin.headers,
            )

    def test_org_override_secret_is_encrypted(
        self, e2e_client, platform_admin, integration_with_secret_schema, org1
    ):
        """Secret config values saved via org mapping overrides are encrypted."""
        integration = integration_with_secret_schema

        # Set defaults
        e2e_client.put(
            f"/api/integrations/{integration['id']}/config",
            headers=platform_admin.headers,
            json={
                "config": {
                    "base_url": "https://api.default.com",
                    "api_key": "default-key",
                }
            },
        )

        # Create mapping with org-specific secret override
        response = e2e_client.post(
            f"/api/integrations/{integration['id']}/mappings",
            headers=platform_admin.headers,
            json={
                "organization_id": str(org1["id"]),
                "entity_id": "org-secret-test",
                "config": {
                    "api_key": "org-specific-secret-key",
                },
            },
        )
        assert response.status_code == 201
        mapping = response.json()

        try:
            # SDK should return the org override (decrypted)
            response = e2e_client.get(
                f"/api/integrations/sdk/{integration['name']}",
                headers=platform_admin.headers,
                params={"org_id": str(org1["id"])},
            )
            assert response.status_code == 200
            data = response.json()

            assert data["config"]["api_key"] == "org-specific-secret-key"
            assert data["config"]["base_url"] == "https://api.default.com"
        finally:
            e2e_client.delete(
                f"/api/integrations/{integration['id']}/mappings/{mapping['id']}",
                headers=platform_admin.headers,
            )
```

**Step 2: Run the test to verify it fails**

Run: `./test.sh tests/e2e/api/test_integrations.py::TestIntegrationConfigSecrets -v`
Expected: FAIL — `config_type` is STRING not SECRET, value is not masked

**Step 3: Fix `_save_config()` to set `config_type` and encrypt secrets**

In `api/src/routers/integrations.py`, modify `_save_config()`:

```python
async def _save_config(
    self,
    integration_id: UUID,
    organization_id: UUID | None,
    config: dict[str, Any],
    updated_by: str = "system",
) -> None:
    """
    Persist config values to the configs table.

    For each key-value pair:
    - If value is None or empty string, delete the entry (fall back to default)
    - Otherwise, upsert the entry
    - Sets config_type based on integration config schema
    - Encrypts secret values before storage

    Uses explicit SELECT + INSERT/UPDATE pattern because PostgreSQL's
    ON CONFLICT doesn't work with functional indexes (COALESCE for NULL handling).
    """
    from src.core.security import encrypt_secret
    from src.models.enums import ConfigType as ConfigTypeEnum

    # Look up schema items for this integration to get config_schema_id
    schema_result = await self.db.execute(
        select(IntegrationConfigSchema)
        .where(IntegrationConfigSchema.integration_id == integration_id)
    )
    schema_items = {item.key: item for item in schema_result.scalars().all()}

    # Map schema type strings to ConfigTypeEnum
    SCHEMA_TYPE_MAP = {
        "string": ConfigTypeEnum.STRING,
        "int": ConfigTypeEnum.INT,
        "bool": ConfigTypeEnum.BOOL,
        "json": ConfigTypeEnum.JSON,
        "secret": ConfigTypeEnum.SECRET,
    }

    for key, value in config.items():
        # Get the schema item for this key (for FK reference)
        schema_item = schema_items.get(key)

        # Validate value against schema type if schema exists
        if schema_item:
            await self._validate_config_value(key, value, schema_item.type)

        # Determine config_type from schema
        db_config_type = ConfigTypeEnum.STRING
        if schema_item:
            db_config_type = SCHEMA_TYPE_MAP.get(schema_item.type, ConfigTypeEnum.STRING)

        # Build the WHERE clause for matching existing config
        # Handle NULL comparison properly with IS NULL
        if organization_id is None:
            where_clause = and_(
                ConfigModel.integration_id == integration_id,
                ConfigModel.organization_id.is_(None),
                ConfigModel.key == key,
            )
        else:
            where_clause = and_(
                ConfigModel.integration_id == integration_id,
                ConfigModel.organization_id == organization_id,
                ConfigModel.key == key,
            )

        if value is None or value == "":
            # Delete override (fall back to default)
            await self.db.execute(delete(ConfigModel).where(where_clause))
        else:
            # Encrypt secret values before storage
            stored_value = value
            if db_config_type == ConfigTypeEnum.SECRET and isinstance(value, str):
                stored_value = encrypt_secret(value)

            # Check if record exists
            result = await self.db.execute(
                select(ConfigModel.id).where(where_clause)
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing record
                from sqlalchemy import update
                await self.db.execute(
                    update(ConfigModel)
                    .where(ConfigModel.id == existing)
                    .values(
                        value={"value": stored_value},
                        config_type=db_config_type,
                        updated_by=updated_by,
                        config_schema_id=schema_item.id if schema_item else None,
                    )
                )
            else:
                # Insert new record
                new_config = ConfigModel(
                    integration_id=integration_id,
                    organization_id=organization_id,
                    key=key,
                    value={"value": stored_value},
                    config_type=db_config_type,
                    updated_by=updated_by,
                    config_schema_id=schema_item.id if schema_item else None,
                )
                self.db.add(new_config)

    # Flush changes so they're visible to subsequent queries
    await self.db.flush()
```

**Step 4: Fix read paths to decrypt secrets**

In `api/src/routers/integrations.py`, create a helper and update the three read methods:

```python
# Add this helper method to IntegrationsRepository, right before get_integration_defaults

async def _extract_config_value(self, entry: ConfigModel) -> Any:
    """Extract config value, decrypting secrets."""
    from src.core.security import decrypt_secret
    from src.models.enums import ConfigType as ConfigTypeEnum

    value = entry.value
    if isinstance(value, dict) and "value" in value:
        raw = value["value"]
    else:
        raw = value

    if entry.config_type == ConfigTypeEnum.SECRET and isinstance(raw, str):
        try:
            return decrypt_secret(raw)
        except Exception:
            # Value may not be encrypted yet (pre-migration data)
            return raw
    return raw
```

Then update `get_integration_defaults`:
```python
async def get_integration_defaults(self, integration_id: UUID) -> dict[str, Any]:
    config_query = select(ConfigModel).where(
        and_(
            ConfigModel.integration_id == integration_id,
            ConfigModel.organization_id.is_(None),
        )
    )
    result = await self.db.execute(config_query)
    config_entries = result.scalars().all()

    config: dict[str, Any] = {}
    for entry in config_entries:
        config[entry.key] = await self._extract_config_value(entry)

    return config
```

Apply the same pattern to `get_org_config_overrides` and `get_all_org_config_overrides`.

**Step 5: Run tests to verify they pass**

Run: `./test.sh tests/e2e/api/test_integrations.py::TestIntegrationConfigSecrets -v`
Expected: PASS

**Step 6: Run the full integration test suite to check for regressions**

Run: `./test.sh tests/e2e/api/test_integrations.py -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add api/src/routers/integrations.py api/tests/e2e/api/test_integrations.py
git commit -m "fix: encrypt secret config values in integration _save_config and decrypt on read"
```

---

### Task 2: Add integration info to ConfigResponse and Config list page

**Files:**
- Modify: `api/src/models/contracts/config.py` — add `integration_id` and `integration_name`
- Modify: `api/src/routers/config.py` — join Integration to get name
- Modify: `client/src/pages/Config.tsx` — add Integration column
- Modify: `client/src/lib/v1.d.ts` — regenerate types

**Step 1: Add fields to ConfigResponse**

In `api/src/models/contracts/config.py`, add to `ConfigResponse`:

```python
class ConfigResponse(BaseModel):
    """Configuration entity response (global or org-specific)"""
    id: UUID | None = Field(default=None, description="Config UUID")
    key: str
    value: Any = Field(..., description="Config value. For SECRET type, this will be '[SECRET]' in list responses.")
    type: ConfigType = ConfigType.STRING
    scope: Literal["GLOBAL", "org"] = Field(
        default="org", description="GLOBAL for MSP-wide or 'org' for org-specific")
    org_id: str | None = Field(
        default=None, description="Organization ID (only for org-specific config)")
    integration_id: str | None = Field(
        default=None, description="Integration ID (if config is managed by an integration)")
    integration_name: str | None = Field(
        default=None, description="Integration name (if config is managed by an integration)")
    description: str | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None
```

**Step 2: Update `list_configs` to join Integration**

In `api/src/routers/config.py`, modify `list_configs` to include integration info:

```python
async def list_configs(
    self,
    filter_type: OrgFilterType = OrgFilterType.ORG_PLUS_GLOBAL,
) -> list[ConfigResponse]:
    from src.models.orm.integrations import Integration

    query = select(self.model, Integration.name.label("integration_name")).outerjoin(
        Integration,
        and_(
            self.model.integration_id == Integration.id,
            Integration.is_deleted.is_(False),
        )
    )

    # Apply filter based on filter_type
    if filter_type == OrgFilterType.ALL:
        pass
    elif filter_type == OrgFilterType.GLOBAL_ONLY:
        query = query.where(self.model.organization_id.is_(None))
    elif filter_type == OrgFilterType.ORG_ONLY:
        query = query.where(self.model.organization_id == self.org_id)
    else:
        query = self._apply_cascade_scope(query)

    query = query.order_by(self.model.key)

    result = await self.session.execute(query)
    rows = result.all()

    schemas = []
    for row in rows:
        c = row[0]  # ConfigModel
        integration_name = row[1]  # Integration.name or None

        raw_value = c.value.get("value") if isinstance(c.value, dict) else c.value
        # Mask secret values in list responses
        if c.config_type == ConfigTypeEnum.SECRET:
            display_value = "[SECRET]"
        else:
            display_value = raw_value

        schemas.append(
            ConfigResponse(
                id=c.id,
                key=c.key,
                value=display_value,
                type=ConfigType(c.config_type.value) if c.config_type else ConfigType.STRING,
                scope="org" if c.organization_id else "GLOBAL",
                org_id=str(c.organization_id) if c.organization_id else None,
                integration_id=str(c.integration_id) if c.integration_id else None,
                integration_name=integration_name,
                description=c.description,
                updated_at=c.updated_at,
                updated_by=c.updated_by,
            )
        )
    return schemas
```

Note: You need to add `from sqlalchemy import and_` to imports in `config.py` if not already present.

**Step 3: Regenerate TypeScript types**

Run: `cd client && npm run generate:types`

**Step 4: Update Config.tsx to show Integration column**

In `client/src/pages/Config.tsx`, add a column after the "Key" column:

```tsx
{/* In the DataTableHeader */}
<DataTableHead>Key</DataTableHead>
<DataTableHead className="w-0 whitespace-nowrap">Integration</DataTableHead>

{/* In each DataTableRow */}
<DataTableCell className="font-mono">
    {config.key}
</DataTableCell>
<DataTableCell className="w-0 whitespace-nowrap">
    {config.integration_name ? (
        <Badge variant="outline" className="text-xs">
            {config.integration_name}
        </Badge>
    ) : (
        <span className="text-muted-foreground">-</span>
    )}
</DataTableCell>
```

**Step 5: Run frontend type check**

Run: `cd client && npm run tsc`
Expected: PASS

**Step 6: Run backend tests**

Run: `./test.sh tests/e2e/api/test_integrations.py -v`
Expected: All PASS (the E2E test from Task 1 verifies integration_id is present in config list)

**Step 7: Commit**

```bash
git add api/src/models/contracts/config.py api/src/routers/config.py client/src/pages/Config.tsx client/src/lib/v1.d.ts
git commit -m "feat: show integration name in Configuration list page"
```

---

### Task 3: Data migration to backfill existing integration config secrets

**Files:**
- Create: `api/alembic/versions/XXXX_backfill_integration_config_types.py`

**Step 1: Create the migration**

Run: `cd api && alembic revision -m "backfill integration config types and encrypt secrets"`

**Step 2: Write the migration**

The migration should:
1. Query all `configs` rows that have `integration_id IS NOT NULL`
2. Join `integration_config_schema` on `(config.integration_id, config.key)` to get the schema type
3. For each row: update `config_type` to match schema type
4. For secret-type rows: encrypt the plaintext value

```python
"""backfill integration config types and encrypt secrets

Revision ID: XXXX
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'XXXX'
down_revision = '<previous>'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Backfill config_type from integration schema and encrypt secret values."""
    from src.core.security import encrypt_secret

    conn = op.get_bind()

    # Find all configs with integration_id that need backfill
    rows = conn.execute(sa.text("""
        SELECT c.id, c.key, c.value, c.config_type, ics.type as schema_type
        FROM configs c
        JOIN integration_config_schema ics
          ON ics.integration_id = c.integration_id AND ics.key = c.key
        WHERE c.integration_id IS NOT NULL
    """)).fetchall()

    for row in rows:
        config_id = row.id
        current_type = row.config_type
        schema_type = row.schema_type
        value = row.value

        # Skip if config_type already matches schema
        if current_type == schema_type:
            continue

        # Update config_type to match schema
        update_values = {"config_type": schema_type}

        # For secrets, encrypt the plaintext value
        if schema_type == "secret":
            raw = value.get("value") if isinstance(value, dict) else value
            if isinstance(raw, str):
                # Only encrypt if it doesn't look already encrypted
                # (Fernet tokens start with 'gAAA')
                if not raw.startswith("gAAA"):
                    encrypted = encrypt_secret(raw)
                    update_values["value"] = sa.text("jsonb_build_object('value', :enc_val)")

        if "value" in update_values:
            conn.execute(
                sa.text(
                    "UPDATE configs SET config_type = :schema_type, "
                    "value = jsonb_build_object('value', :enc_val) "
                    "WHERE id = :config_id"
                ),
                {
                    "schema_type": schema_type,
                    "enc_val": encrypt_secret(
                        value.get("value") if isinstance(value, dict) else value
                    ),
                    "config_id": config_id,
                },
            )
        else:
            conn.execute(
                sa.text(
                    "UPDATE configs SET config_type = :schema_type WHERE id = :config_id"
                ),
                {"schema_type": schema_type, "config_id": config_id},
            )


def downgrade() -> None:
    """No downgrade - encryption is one-way for security."""
    pass
```

**Step 3: Run the migration in the test environment**

Run: `./test.sh tests/e2e/api/test_integrations.py::TestIntegrationConfigSecrets -v`
Expected: PASS

**Step 4: Commit**

```bash
git add api/alembic/versions/*backfill_integration_config*.py
git commit -m "migration: backfill integration config types and encrypt existing secrets"
```

---

### Task 4: Final verification

**Step 1: Run pyright**

Run: `cd api && pyright`
Expected: 0 errors

**Step 2: Run ruff**

Run: `cd api && ruff check .`
Expected: PASS

**Step 3: Run full backend test suite**

Run: `./test.sh`
Expected: All PASS

**Step 4: Run frontend checks**

Run: `cd client && npm run tsc && npm run lint`
Expected: PASS

**Step 5: Commit any fixes if needed**
