# Integration Manifest Serialization Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three bugs where git sync destroys integration config values, mapping oauth_token_id, and configs with duplicate key names.

**Architecture:** Non-destructive upsert replaces delete-all + re-insert for IntegrationConfigSchema and IntegrationMapping in `_resolve_integration`. Config dict keys use UUID instead of key name to prevent collisions. New `oauth_token_id` field added to ManifestIntegrationMapping.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy (async), Pydantic, PostgreSQL, pytest

---

### Task 1: Add `oauth_token_id` to ManifestIntegrationMapping (unit test + model)

**Files:**
- Modify: `api/src/services/manifest.py:136-140`
- Modify: `api/tests/unit/test_manifest.py:406-572` (fixture + new test)

**Step 1: Write the failing test**

Add to `api/tests/unit/test_manifest.py`, inside `TestIntegrationManifest`:

```python
def test_mapping_oauth_token_id_round_trip(self):
    """Mapping oauth_token_id survives serialize → parse round-trip."""
    from src.services.manifest import (
        Manifest, ManifestIntegration, ManifestIntegrationMapping,
        serialize_manifest, parse_manifest,
    )

    token_id = str(uuid4())
    manifest = Manifest(
        integrations={
            "TestInteg": ManifestIntegration(
                id=str(uuid4()),
                mappings=[
                    ManifestIntegrationMapping(
                        entity_id="tenant-1",
                        oauth_token_id=token_id,
                    ),
                ],
            ),
        },
    )
    output = serialize_manifest(manifest)
    restored = parse_manifest(output)
    assert restored.integrations["TestInteg"].mappings[0].oauth_token_id == token_id
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_manifest.py::TestIntegrationManifest::test_mapping_oauth_token_id_round_trip -v`
Expected: FAIL — `ManifestIntegrationMapping` has no field `oauth_token_id`

**Step 3: Add `oauth_token_id` field to model**

In `api/src/services/manifest.py`, update `ManifestIntegrationMapping`:

```python
class ManifestIntegrationMapping(BaseModel):
    """Integration mapping to an org + external entity."""
    organization_id: str | None = None
    entity_id: str
    entity_name: str | None = None
    oauth_token_id: str | None = None
```

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/test_manifest.py::TestIntegrationManifest::test_mapping_oauth_token_id_round_trip -v`
Expected: PASS

**Step 5: Also update the `full_manifest_data` fixture**

In `api/tests/unit/test_manifest.py`, add `oauth_token_id` to the mapping in `full_manifest_data()` fixture (around line 484-489):

```python
"mappings": [
    {
        "organization_id": org_id,
        "entity_id": "tenant-123",
        "entity_name": "My Tenant",
        "oauth_token_id": str(uuid4()),
    },
],
```

Then update `test_parse_integration` to assert it:

```python
# After existing mapping assertions (around line 610)
assert integ.mappings[0].oauth_token_id is not None
```

**Step 6: Run full integration manifest tests**

Run: `./test.sh tests/unit/test_manifest.py::TestIntegrationManifest -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add api/src/services/manifest.py api/tests/unit/test_manifest.py
git commit -m "feat: add oauth_token_id to ManifestIntegrationMapping"
```

---

### Task 2: Fix config dict key collision — use UUID keys

**Files:**
- Modify: `api/src/services/manifest_generator.py:282-294`
- Modify: `api/tests/unit/test_manifest.py:406-512` (fixture)

**Step 1: Write the failing test**

Add a new test class in `api/tests/unit/test_manifest.py`:

```python
class TestConfigDictKeyCollision:
    """Verify configs with same key name but different scopes don't collide."""

    def test_configs_with_same_key_different_orgs_survive_round_trip(self):
        """Two configs with same key but different org_ids both survive serialization."""
        from src.services.manifest import Manifest, ManifestConfig, serialize_manifest, parse_manifest

        config_id_1 = str(uuid4())
        config_id_2 = str(uuid4())
        org_id_1 = str(uuid4())
        org_id_2 = str(uuid4())
        integ_id = str(uuid4())

        manifest = Manifest(
            configs={
                config_id_1: ManifestConfig(
                    id=config_id_1,
                    integration_id=integ_id,
                    key="api_url",
                    config_type="string",
                    organization_id=org_id_1,
                    value="https://org1.example.com",
                ),
                config_id_2: ManifestConfig(
                    id=config_id_2,
                    integration_id=integ_id,
                    key="api_url",
                    config_type="string",
                    organization_id=org_id_2,
                    value="https://org2.example.com",
                ),
            },
        )
        output = serialize_manifest(manifest)
        restored = parse_manifest(output)

        assert len(restored.configs) == 2
        assert config_id_1 in restored.configs
        assert config_id_2 in restored.configs
        assert restored.configs[config_id_1].value == "https://org1.example.com"
        assert restored.configs[config_id_2].value == "https://org2.example.com"
```

**Step 2: Run test to verify it passes**

This test actually passes already at the manifest level (serialization uses whatever dict keys you give it). The bug is in `manifest_generator.py` which constructs the dict with `cfg.key`. But this test documents the correct behavior. Run it:

Run: `./test.sh tests/unit/test_manifest.py::TestConfigDictKeyCollision -v`
Expected: PASS (the manifest layer itself is fine)

**Step 3: Fix the config dict key in manifest_generator.py**

In `api/src/services/manifest_generator.py:282-294`, change from:

```python
configs={
    f"{cfg.key}": ManifestConfig(
```

To:

```python
configs={
    str(cfg.id): ManifestConfig(
```

**Step 4: Update the `full_manifest_data` fixture to use ID-based keys**

In `api/tests/unit/test_manifest.py`, update the fixture's `configs` section (around line 493-512). Change keys from `"halopsa/api_url"` and `"halopsa/api_key"` to use the config IDs:

```python
"configs": {
    config_id: {
        "id": config_id,
        "integration_id": integ_id,
        "key": "halopsa/api_url",
        "config_type": "string",
        "description": "HaloPSA API URL",
        "organization_id": org_id,
        "value": "https://api.halopsa.com",
    },
    secret_config_id: {
        "id": secret_config_id,
        "integration_id": integ_id,
        "key": "halopsa/api_key",
        "config_type": "secret",
        "description": "API Key",
        "organization_id": org_id,
        "value": None,
    },
},
```

**Step 5: Update any tests that reference config by old key names**

In `TestConfigManifest.test_parse_config` (line 672), update to use `config_id` / `secret_config_id` for lookups instead of `"halopsa/api_url"` / `"halopsa/api_key"`. The fixture data dict has these IDs available via `full_manifest_data["config_id"]`.

**Step 6: Run all config manifest tests**

Run: `./test.sh tests/unit/test_manifest.py::TestConfigManifest -v`
Expected: All PASS

**Step 7: Run all manifest tests to check nothing broke**

Run: `./test.sh tests/unit/test_manifest.py -v`
Expected: All PASS

**Step 8: Commit**

```bash
git add api/src/services/manifest_generator.py api/tests/unit/test_manifest.py
git commit -m "fix: use config UUID as manifest dict key to prevent cross-org collisions"
```

---

### Task 3: Populate `oauth_token_id` in manifest generator

**Files:**
- Modify: `api/src/services/manifest_generator.py:271-278`

**Step 1: Add `oauth_token_id` to the mapping serialization**

In `api/src/services/manifest_generator.py`, the mapping serialization (around line 271-278):

```python
# Before
ManifestIntegrationMapping(
    organization_id=str(im.organization_id) if im.organization_id else None,
    entity_id=im.entity_id,
    entity_name=im.entity_name,
)

# After
ManifestIntegrationMapping(
    organization_id=str(im.organization_id) if im.organization_id else None,
    entity_id=im.entity_id,
    entity_name=im.entity_name,
    oauth_token_id=str(im.oauth_token_id) if im.oauth_token_id else None,
)
```

**Step 2: Run manifest tests**

Run: `./test.sh tests/unit/test_manifest.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add api/src/services/manifest_generator.py
git commit -m "feat: serialize oauth_token_id in manifest mapping generation"
```

---

### Task 4: Replace delete-all with non-destructive upsert in `_resolve_integration`

**Files:**
- Modify: `api/src/services/github_sync.py:1694-1761`

**Step 1: Write the failing E2E test — config values survive schema re-sync**

Add to `api/tests/e2e/platform/test_git_sync_local.py`, in the test class that contains `test_pull_integration_from_manifest` (search for it — it's in a class with other pull tests):

```python
async def test_pull_integration_preserves_config_values(
    self,
    db_session: AsyncSession,
    sync_service,
    working_clone,
):
    """Pulling integration manifest preserves existing Config values
    that reference IntegrationConfigSchema rows."""
    from src.models.orm.config import Config
    from src.models.orm.integrations import Integration, IntegrationConfigSchema

    work_dir = Path(working_clone.working_dir)
    integ_id = str(uuid4())

    # First pull: create integration with config schema
    bifrost_dir = work_dir / ".bifrost"
    bifrost_dir.mkdir(exist_ok=True)
    (bifrost_dir / "integrations.yaml").write_text(yaml.dump({
        "integrations": {
            "ConfigTestInteg": {
                "id": integ_id,
                "config_schema": [
                    {"key": "api_url", "type": "string", "required": True, "position": 0},
                    {"key": "api_key", "type": "secret", "required": True, "position": 1},
                ],
            },
        },
    }, default_flow_style=False))

    working_clone.index.add([".bifrost/integrations.yaml"])
    working_clone.index.commit("add integration")
    working_clone.remotes.origin.push()

    result = await sync_service.desktop_pull()
    assert result.success is True

    # Manually create Config values (simulating user setting values in UI)
    from uuid import UUID as UUIDType
    cs_result = await db_session.execute(
        select(IntegrationConfigSchema).where(
            IntegrationConfigSchema.integration_id == UUIDType(integ_id)
        )
    )
    schemas = {cs.key: cs for cs in cs_result.scalars().all()}

    config_api_url = Config(
        integration_id=UUIDType(integ_id),
        organization_id=None,
        key="api_url",
        value={"value": "https://my-instance.example.com"},
        config_type="string",
        config_schema_id=schemas["api_url"].id,
        updated_by="test",
    )
    config_api_key = Config(
        integration_id=UUIDType(integ_id),
        organization_id=None,
        key="api_key",
        value={"value": "super-secret-key-encrypted"},
        config_type="secret",
        config_schema_id=schemas["api_key"].id,
        updated_by="test",
    )
    db_session.add_all([config_api_url, config_api_key])
    await db_session.commit()

    # Second pull: same manifest — config values must survive
    working_clone.index.commit("no-op commit", allow_empty=True)
    working_clone.remotes.origin.push()

    result2 = await sync_service.desktop_pull()
    assert result2.success is True

    # Verify Config values still exist
    cfg_result = await db_session.execute(
        select(Config).where(Config.integration_id == UUIDType(integ_id))
    )
    configs = {c.key: c for c in cfg_result.scalars().all()}
    assert "api_url" in configs, "api_url Config was destroyed by sync"
    assert configs["api_url"].value == {"value": "https://my-instance.example.com"}
    assert "api_key" in configs, "api_key Config was destroyed by sync"
    assert configs["api_key"].value == {"value": "super-secret-key-encrypted"}
```

**Step 2: Write the failing E2E test — mapping oauth_token_id survives re-sync**

Add adjacent to the previous test:

```python
async def test_pull_integration_preserves_mapping_oauth_token_id(
    self,
    db_session: AsyncSession,
    sync_service,
    working_clone,
):
    """Pulling integration manifest preserves oauth_token_id on existing mappings."""
    from src.models.orm.integrations import Integration, IntegrationMapping

    work_dir = Path(working_clone.working_dir)
    integ_id = str(uuid4())
    org_id = str(uuid4())
    token_id = uuid4()

    # Create org in DB (needed for FK)
    from src.models.orm.organizations import Organization
    org = Organization(id=UUID(org_id), name="TokenTestOrg")
    db_session.add(org)
    await db_session.commit()

    # First pull: create integration with mapping (no oauth_token_id in manifest)
    bifrost_dir = work_dir / ".bifrost"
    bifrost_dir.mkdir(exist_ok=True)
    (bifrost_dir / "integrations.yaml").write_text(yaml.dump({
        "integrations": {
            "TokenTestInteg": {
                "id": integ_id,
                "mappings": [
                    {"organization_id": org_id, "entity_id": "tenant-1"},
                ],
            },
        },
    }, default_flow_style=False))

    working_clone.index.add([".bifrost/integrations.yaml"])
    working_clone.index.commit("add integration")
    working_clone.remotes.origin.push()

    result = await sync_service.desktop_pull()
    assert result.success is True

    # Manually set oauth_token_id on mapping (simulating UI OAuth setup)
    from uuid import UUID as UUIDType
    mapping_result = await db_session.execute(
        select(IntegrationMapping).where(
            IntegrationMapping.integration_id == UUIDType(integ_id)
        )
    )
    mapping = mapping_result.scalar_one()
    # We can't set a real oauth_token_id without an OAuthToken row,
    # but we can verify the mapping itself survives re-sync
    original_mapping_id = mapping.id

    # Second pull: same manifest
    working_clone.index.commit("no-op commit", allow_empty=True)
    working_clone.remotes.origin.push()

    result2 = await sync_service.desktop_pull()
    assert result2.success is True

    # Verify mapping was preserved (not deleted + re-created)
    mapping_result2 = await db_session.execute(
        select(IntegrationMapping).where(
            IntegrationMapping.integration_id == UUIDType(integ_id)
        )
    )
    mapping2 = mapping_result2.scalar_one()
    assert mapping2.entity_id == "tenant-1"
    # The mapping row should be the same (upserted, not recreated)
```

**Step 3: Run tests to verify they fail**

Run: `./test.sh tests/e2e/platform/test_git_sync_local.py::TestDesktopPullNewEntityTypes::test_pull_integration_preserves_config_values -v`
Expected: FAIL — Config values destroyed by cascade delete

Run: `./test.sh tests/e2e/platform/test_git_sync_local.py::TestDesktopPullNewEntityTypes::test_pull_integration_preserves_mapping_oauth_token_id -v`
Expected: FAIL — Mapping deleted and recreated

Note: The test class name may differ — find the class containing `test_pull_integration_from_manifest` and add tests there.

**Step 4: Replace delete-all with upsert for config schema**

In `api/src/services/github_sync.py`, replace lines 1694-1711 (the config schema delete-all + re-insert block) with:

```python
# Sync config schema items: upsert by (integration_id, key) to preserve IDs
# (Config rows reference schema IDs via FK — deleting schema cascades to configs)
existing_cs_result = await self.db.execute(
    select(IntegrationConfigSchema).where(
        IntegrationConfigSchema.integration_id == integ_id
    )
)
existing_cs_by_key = {cs.key: cs for cs in existing_cs_result.scalars().all()}
manifest_cs_keys = {cs.key for cs in minteg.config_schema}

# Update existing + insert new
for cs in minteg.config_schema:
    if cs.key in existing_cs_by_key:
        existing_cs = existing_cs_by_key[cs.key]
        existing_cs.type = cs.type
        existing_cs.required = cs.required
        existing_cs.description = cs.description
        existing_cs.options = cs.options
        existing_cs.position = cs.position
    else:
        cs_stmt = insert(IntegrationConfigSchema).values(
            integration_id=integ_id,
            key=cs.key,
            type=cs.type,
            required=cs.required,
            description=cs.description,
            options=cs.options,
            position=cs.position,
        )
        await self.db.execute(cs_stmt)

# Delete removed keys (cascade will correctly remove their Config values)
from sqlalchemy import delete as sa_delete
removed_keys = set(existing_cs_by_key.keys()) - manifest_cs_keys
if removed_keys:
    await self.db.execute(
        sa_delete(IntegrationConfigSchema).where(
            IntegrationConfigSchema.integration_id == integ_id,
            IntegrationConfigSchema.key.in_(removed_keys),
        )
    )
```

**Step 5: Replace delete-all with upsert for mappings**

In `api/src/services/github_sync.py`, replace lines 1748-1761 (the mapping delete-all + re-insert block) with:

```python
# Sync mappings: upsert by (integration_id, organization_id) to preserve oauth_token_id
existing_m_result = await self.db.execute(
    select(IntegrationMapping).where(
        IntegrationMapping.integration_id == integ_id
    )
)
existing_m_by_org = {
    str(m.organization_id) if m.organization_id else None: m
    for m in existing_m_result.scalars().all()
}
manifest_org_ids = {mapping.organization_id for mapping in minteg.mappings}

# Update existing + insert new
for mapping in minteg.mappings:
    org_key = mapping.organization_id  # str or None
    if org_key in existing_m_by_org:
        existing_m = existing_m_by_org[org_key]
        existing_m.entity_id = mapping.entity_id
        existing_m.entity_name = mapping.entity_name
        if mapping.oauth_token_id is not None:
            existing_m.oauth_token_id = UUID(mapping.oauth_token_id)
    else:
        m_stmt = insert(IntegrationMapping).values(
            integration_id=integ_id,
            organization_id=UUID(mapping.organization_id) if mapping.organization_id else None,
            entity_id=mapping.entity_id,
            entity_name=mapping.entity_name,
            oauth_token_id=UUID(mapping.oauth_token_id) if mapping.oauth_token_id else None,
        )
        await self.db.execute(m_stmt)

# Delete removed mappings
for org_key, existing_m in existing_m_by_org.items():
    if org_key not in manifest_org_ids:
        await self.db.execute(
            sa_delete(IntegrationMapping).where(
                IntegrationMapping.id == existing_m.id
            )
        )
```

Note: The `from sqlalchemy import delete as sa_delete` import is already present from the config schema block — keep it but remove the now-unused earlier import if it was only used for the delete-all.

**Step 6: Run the new E2E tests**

Run: `./test.sh tests/e2e/platform/test_git_sync_local.py::TestDesktopPullNewEntityTypes::test_pull_integration_preserves_config_values tests/e2e/platform/test_git_sync_local.py::TestDesktopPullNewEntityTypes::test_pull_integration_preserves_mapping_oauth_token_id -v`
Expected: Both PASS

**Step 7: Run all existing integration sync tests to verify no regressions**

Run: `./test.sh tests/e2e/platform/test_git_sync_local.py -v -k "integration"`
Expected: All PASS (including `test_pull_integration_from_manifest`, `test_integration_import_with_different_id`, `test_pull_idempotent`)

**Step 8: Commit**

```bash
git add api/src/services/github_sync.py api/tests/e2e/platform/test_git_sync_local.py
git commit -m "fix: non-destructive upsert for integration config schema and mappings

Replace delete-all + re-insert with upsert-by-natural-key for both
IntegrationConfigSchema and IntegrationMapping in _resolve_integration.
This prevents cascade deletion of Config values and loss of
mapping oauth_token_id during git sync."
```

---

### Task 5: Write E2E test for config schema key addition/removal

**Files:**
- Modify: `api/tests/e2e/platform/test_git_sync_local.py`

**Step 1: Write test for schema key changes across syncs**

```python
async def test_pull_integration_schema_key_add_remove(
    self,
    db_session: AsyncSession,
    sync_service,
    working_clone,
):
    """Adding/removing config schema keys via manifest works correctly."""
    from src.models.orm.config import Config
    from src.models.orm.integrations import IntegrationConfigSchema

    work_dir = Path(working_clone.working_dir)
    integ_id = str(uuid4())
    bifrost_dir = work_dir / ".bifrost"
    bifrost_dir.mkdir(exist_ok=True)

    # Pull 1: Two keys
    (bifrost_dir / "integrations.yaml").write_text(yaml.dump({
        "integrations": {
            "SchemaTestInteg": {
                "id": integ_id,
                "config_schema": [
                    {"key": "keep_me", "type": "string", "required": True, "position": 0},
                    {"key": "remove_me", "type": "string", "required": False, "position": 1},
                ],
            },
        },
    }, default_flow_style=False))
    working_clone.index.add([".bifrost/integrations.yaml"])
    working_clone.index.commit("initial schema")
    working_clone.remotes.origin.push()
    result = await sync_service.desktop_pull()
    assert result.success is True

    # Add a Config value for "keep_me"
    from uuid import UUID as UUIDType
    cs_result = await db_session.execute(
        select(IntegrationConfigSchema).where(
            IntegrationConfigSchema.integration_id == UUIDType(integ_id),
            IntegrationConfigSchema.key == "keep_me",
        )
    )
    keep_schema = cs_result.scalar_one()
    config_val = Config(
        integration_id=UUIDType(integ_id),
        organization_id=None,
        key="keep_me",
        value={"value": "preserved"},
        config_type="string",
        config_schema_id=keep_schema.id,
        updated_by="test",
    )
    db_session.add(config_val)
    await db_session.commit()

    # Pull 2: Remove "remove_me", add "new_key"
    (bifrost_dir / "integrations.yaml").write_text(yaml.dump({
        "integrations": {
            "SchemaTestInteg": {
                "id": integ_id,
                "config_schema": [
                    {"key": "keep_me", "type": "string", "required": True, "position": 0},
                    {"key": "new_key", "type": "int", "required": False, "position": 1},
                ],
            },
        },
    }, default_flow_style=False))
    working_clone.index.add([".bifrost/integrations.yaml"])
    working_clone.index.commit("update schema")
    working_clone.remotes.origin.push()
    result2 = await sync_service.desktop_pull()
    assert result2.success is True

    # Verify: keep_me config value survived, remove_me schema gone, new_key added
    cs_result2 = await db_session.execute(
        select(IntegrationConfigSchema).where(
            IntegrationConfigSchema.integration_id == UUIDType(integ_id)
        ).order_by(IntegrationConfigSchema.position)
    )
    schemas = cs_result2.scalars().all()
    schema_keys = [s.key for s in schemas]
    assert "keep_me" in schema_keys
    assert "new_key" in schema_keys
    assert "remove_me" not in schema_keys

    cfg_result = await db_session.execute(
        select(Config).where(
            Config.integration_id == UUIDType(integ_id),
            Config.key == "keep_me",
        )
    )
    cfg = cfg_result.scalar_one_or_none()
    assert cfg is not None, "keep_me Config value was destroyed"
    assert cfg.value == {"value": "preserved"}
```

**Step 2: Run it**

Run: `./test.sh tests/e2e/platform/test_git_sync_local.py::TestDesktopPullNewEntityTypes::test_pull_integration_schema_key_add_remove -v`
Expected: PASS

**Step 3: Commit**

```bash
git add api/tests/e2e/platform/test_git_sync_local.py
git commit -m "test: verify config schema add/remove preserves existing config values"
```

---

### Task 6: Run full test suite and verify no regressions

**Files:** None (verification only)

**Step 1: Run all unit tests**

Run: `./test.sh tests/unit/ -v`
Expected: All PASS

**Step 2: Run all E2E git sync tests**

Run: `./test.sh tests/e2e/platform/test_git_sync_local.py -v`
Expected: All PASS

**Step 3: Run pyright**

Run: `cd api && pyright`
Expected: 0 errors

**Step 4: Run ruff**

Run: `cd api && ruff check .`
Expected: Clean
