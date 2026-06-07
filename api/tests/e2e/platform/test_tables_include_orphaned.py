"""E2E (live REST + DB seed): the tables/configs LIST paths hide orphaned rows by
default and include them (with provenance) when ?include_orphaned=true.

Orphaned rows (former-install data, solution_id NULL'd to survive uninstall,
orphaned_at stamped) must NOT clutter the normal list. T14d-1 already excludes
them from the org name cascade (get(name=)); this covers the list() path so the
UI can offer a "Show orphaned" toggle.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.models.enums import ConfigType as ConfigTypeEnum
from src.models.orm.config import Config
from src.models.orm.tables import Table

pytestmark = pytest.mark.e2e


async def test_tables_list_excludes_orphaned_by_default(
    e2e_client, platform_admin, db_session
):
    headers = platform_admin.headers
    suffix = uuid.uuid4().hex[:8]
    normal_name = f"normal_{suffix}"
    orphan_name = f"orphan_{suffix}"

    normal = Table(
        id=uuid.uuid4(),
        name=normal_name,
        organization_id=None,
        created_by="dev@x",
        access=None,
    )
    orphan = Table(
        id=uuid.uuid4(),
        name=orphan_name,
        organization_id=None,
        solution_id=None,
        origin_solution_slug="acme",
        origin_solution_id=uuid.uuid4(),
        orphaned_at=datetime.now(timezone.utc),
        created_by="dev@x",
        access=None,
    )
    db_session.add_all([normal, orphan])
    await db_session.commit()

    # Default list: orphan absent, normal present.
    r = e2e_client.get("/api/tables", headers=headers)
    assert r.status_code == 200, r.text
    names = {t["name"] for t in r.json()["tables"]}
    assert normal_name in names
    assert orphan_name not in names


async def test_tables_list_include_orphaned_shows_provenance(
    e2e_client, platform_admin, db_session
):
    headers = platform_admin.headers
    suffix = uuid.uuid4().hex[:8]
    normal_name = f"normal_{suffix}"
    orphan_name = f"orphan_{suffix}"

    normal = Table(
        id=uuid.uuid4(),
        name=normal_name,
        organization_id=None,
        created_by="dev@x",
        access=None,
    )
    orphan = Table(
        id=uuid.uuid4(),
        name=orphan_name,
        organization_id=None,
        solution_id=None,
        origin_solution_slug="acme",
        origin_solution_id=uuid.uuid4(),
        orphaned_at=datetime.now(timezone.utc),
        created_by="dev@x",
        access=None,
    )
    db_session.add_all([normal, orphan])
    await db_session.commit()

    r = e2e_client.get("/api/tables?include_orphaned=true", headers=headers)
    assert r.status_code == 200, r.text
    by_name = {t["name"]: t for t in r.json()["tables"]}
    assert normal_name in by_name
    assert orphan_name in by_name
    assert by_name[orphan_name]["origin_solution_slug"] == "acme"
    assert by_name[orphan_name]["orphaned_at"] is not None


async def test_configs_list_excludes_orphaned_by_default(
    e2e_client, platform_admin, db_session
):
    headers = platform_admin.headers
    suffix = uuid.uuid4().hex[:8]
    normal_key = f"normal_{suffix}"
    orphan_key = f"orphan_{suffix}"
    now = datetime.now(timezone.utc)

    normal = Config(
        id=uuid.uuid4(),
        key=normal_key,
        value={"value": "v"},
        config_type=ConfigTypeEnum.STRING,
        organization_id=None,
        created_at=now,
        updated_at=now,
        updated_by="dev@x",
    )
    orphan = Config(
        id=uuid.uuid4(),
        key=orphan_key,
        value={"value": "v"},
        config_type=ConfigTypeEnum.STRING,
        organization_id=None,
        origin_solution_slug="acme",
        origin_solution_id=uuid.uuid4(),
        orphaned_at=now,
        created_at=now,
        updated_at=now,
        updated_by="dev@x",
    )
    db_session.add_all([normal, orphan])
    await db_session.commit()

    r = e2e_client.get("/api/config", headers=headers)
    assert r.status_code == 200, r.text
    keys = {c["key"] for c in r.json()}
    assert normal_key in keys
    assert orphan_key not in keys


async def test_configs_list_include_orphaned_shows_provenance(
    e2e_client, platform_admin, db_session
):
    headers = platform_admin.headers
    suffix = uuid.uuid4().hex[:8]
    orphan_key = f"orphan_{suffix}"
    now = datetime.now(timezone.utc)

    orphan = Config(
        id=uuid.uuid4(),
        key=orphan_key,
        value={"value": "v"},
        config_type=ConfigTypeEnum.STRING,
        organization_id=None,
        origin_solution_slug="acme",
        origin_solution_id=uuid.uuid4(),
        orphaned_at=now,
        created_at=now,
        updated_at=now,
        updated_by="dev@x",
    )
    db_session.add(orphan)
    await db_session.commit()

    r = e2e_client.get("/api/config?include_orphaned=true", headers=headers)
    assert r.status_code == 200, r.text
    by_key = {c["key"]: c for c in r.json()}
    assert orphan_key in by_key
    assert by_key[orphan_key]["origin_solution_slug"] == "acme"
    assert by_key[orphan_key]["orphaned_at"] is not None
