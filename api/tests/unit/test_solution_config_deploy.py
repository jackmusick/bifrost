"""Deploy of solution-owned config DECLARATIONS (values never touched)."""
import pytest
from uuid import uuid4

from sqlalchemy import select

from src.models.orm.solutions import Solution
from src.models.orm.solution_config_schema import SolutionConfigSchema
from src.services.solutions.deploy import (
    SolutionBundle,
    SolutionDeployer,
    SolutionDeployConflict,
    solution_entity_id,
)


def _cfg(cid: str, key: str, *, required: bool = False, ctype: str = "string") -> dict:
    return {"id": cid, "key": key, "type": ctype, "required": required,
            "description": f"{key} desc", "default": None, "position": 0}


async def _make_install(db, slug: str, org_id=None) -> Solution:
    sol = Solution(id=uuid4(), slug=slug, name=slug.upper(), organization_id=org_id)
    db.add(sol)
    await db.flush()
    return sol


@pytest.mark.e2e
class TestSolutionConfigDeploy:
    async def test_bundle_carries_config_schemas(self) -> None:
        b = SolutionBundle(solution=None)  # type: ignore[arg-type]
        assert b.config_schemas == []
        b2 = SolutionBundle(solution=None, config_schemas=[_cfg(str(uuid4()), "K")])  # type: ignore[arg-type]
        assert b2.config_schemas[0]["key"] == "K"

    async def test_deploy_upserts_remapped_declarations(self, db_session) -> None:
        db = db_session
        sol = await _make_install(db, f"cfgdep-{uuid4().hex[:8]}")
        manifest_id = str(uuid4())
        await SolutionDeployer(db).deploy(
            SolutionBundle(solution=sol, config_schemas=[_cfg(manifest_id, "API_KEY", required=True, ctype="secret")])
        )
        await db.flush()
        rows = (await db.execute(
            select(SolutionConfigSchema).where(SolutionConfigSchema.solution_id == sol.id)
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].id == solution_entity_id(sol.id, manifest_id)
        assert rows[0].key == "API_KEY" and rows[0].required is True

    async def test_redeploy_removes_dropped_declaration(self, db_session) -> None:
        db = db_session
        sol = await _make_install(db, f"cfgrec-{uuid4().hex[:8]}")
        a, b = str(uuid4()), str(uuid4())
        await SolutionDeployer(db).deploy(
            SolutionBundle(solution=sol, config_schemas=[_cfg(a, "A"), _cfg(b, "B")])
        )
        await db.flush()
        await SolutionDeployer(db).deploy(
            SolutionBundle(solution=sol, config_schemas=[_cfg(a, "A")])
        )
        await db.flush()
        keys = {r.key for r in (await db.execute(
            select(SolutionConfigSchema).where(SolutionConfigSchema.solution_id == sol.id)
        )).scalars().all()}
        assert keys == {"A"}

    async def test_duplicate_key_in_bundle_is_409(self, db_session) -> None:
        db = db_session
        sol = await _make_install(db, f"cfgdup-{uuid4().hex[:8]}")
        with pytest.raises(SolutionDeployConflict):
            await SolutionDeployer(db).deploy(
                SolutionBundle(solution=sol, config_schemas=[_cfg(str(uuid4()), "X"), _cfg(str(uuid4()), "X")])
            )
