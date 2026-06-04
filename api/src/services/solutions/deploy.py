"""
Solution deploy — full-replace reconcile scoped strictly to ``solution_id``.

Deploy is the single writer for a disconnected install (success-criteria §3.6):
it upserts everything in the bundle and deletes entities previously under THIS
``solution_id`` that are absent from the new bundle. The deletion sweep is
gated on ``WHERE solution_id == sid AND id NOT IN bundle_ids`` — so it can never
touch ``_repo/`` rows (``solution_id IS NULL``) or any other install (a
different ``solution_id``). Scope correctness is by construction, not by a
path-existence heuristic (the destructive global sweep that the viability study
flagged is deliberately NOT reused here).

Python (workflows, modules) installs **as source** to ``_solutions/{id}/`` via
SolutionStorage and is executed as source by the virtual importer (§3.6). Every
deployed entity inherits the install's scope — its ``organization_id`` is the
install's ``organization_id`` (org-scoped or NULL/global), with no per-entity
scope binding (criterion 8).

Sub-plan 1 wires workflows end-to-end (the load-bearing path proven by the
execution criteria). Apps/forms/agents/tables hang off the same reconcile shape
and are added in their sub-plans.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.solutions import Solution
from src.models.orm.workflows import Workflow
from src.services.solutions.storage import SolutionStorage
from src.services.sync_ops import Upsert

logger = logging.getLogger(__name__)


@dataclass
class DeployResult:
    """Counts from one full-replace deploy."""

    workflows_upserted: int = 0
    workflows_deleted: int = 0


@dataclass
class SolutionBundle:
    """The deployable contents of one Solution install.

    ``python_files`` maps relative paths (e.g. ``workflows/w1.py``,
    ``modules/x.py``) to source text, installed verbatim under the install's
    ``_solutions/{id}/`` prefix. ``workflows`` (and, in later sub-plans,
    apps/forms/agents/tables) are manifest-shaped entity dicts to upsert.
    """

    solution: Solution
    python_files: dict[str, str] = field(default_factory=dict)
    workflows: list[dict[str, Any]] = field(default_factory=list)


class SolutionDeployer:
    """Applies a SolutionBundle to storage + DB as a scoped full replace."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def deploy(self, bundle: SolutionBundle) -> DeployResult:
        """Full-replace this install from ``bundle``.

        1. Write Python source to SolutionStorage (_solutions/{id}/).
        2. Upsert bundle entities, stamping solution_id + inherited scope.
        3. Delete entities under THIS solution_id that are absent from the bundle.
        """
        solution = bundle.solution
        sid = solution.id

        await self._write_python(sid, bundle.python_files)
        await self._upsert_workflows(solution, bundle.workflows)
        deleted = await self._reconcile_deletions(sid, bundle)
        return DeployResult(
            workflows_upserted=len(bundle.workflows),
            workflows_deleted=deleted,
        )

    # ── 1. Python source → SolutionStorage ──────────────────────────────────
    async def _write_python(self, sid: UUID, python_files: dict[str, str]) -> None:
        if not python_files:
            return
        storage = SolutionStorage(sid)
        for rel_path, content in python_files.items():
            await storage.write(rel_path, content.encode("utf-8"))

    # ── 2. Entity upserts (stamp solution_id + inherited scope) ──────────────
    async def _upsert_workflows(
        self, solution: Solution, workflows: list[dict[str, Any]]
    ) -> None:
        for mwf in workflows:
            values = {
                "name": mwf["name"],
                "function_name": mwf["function_name"],
                "path": mwf["path"],
                "type": mwf.get("type", "workflow"),
                "is_active": True,
                # Scope is inherited from the install — no per-entity binding.
                "organization_id": solution.organization_id,
                "solution_id": solution.id,
            }
            if mwf.get("description") is not None:
                values["description"] = mwf["description"]
            if mwf.get("access_level") is not None:
                values["access_level"] = mwf["access_level"]
            await Upsert(
                model=Workflow, id=UUID(mwf["id"]), values=values, match_on="id"
            ).execute(self.db)

    # ── 3. Scoped full-replace deletion ─────────────────────────────────────
    async def _reconcile_deletions(self, sid: UUID, bundle: SolutionBundle) -> int:
        """Delete this install's entities that are absent from the bundle.

        Strictly scoped: ``solution_id == sid AND id NOT IN bundle_ids``. Never
        touches _repo/ (solution_id IS NULL) or another install. Returns the
        number of rows deleted.
        """
        return await self._reconcile_one(
            Workflow, sid, {UUID(w["id"]) for w in bundle.workflows}
        )

    async def _reconcile_one(
        self, model: type, sid: UUID, present_ids: set[UUID]
    ) -> int:
        # Find this install's rows that are NOT in the bundle.
        stmt = select(model.id).where(model.solution_id == sid)  # type: ignore[attr-defined]
        existing = set((await self.db.execute(stmt)).scalars().all())
        stale = existing - present_ids
        if not stale:
            return 0
        await self.db.execute(
            delete(model).where(
                model.solution_id == sid,  # type: ignore[attr-defined]
                model.id.in_(stale),  # type: ignore[attr-defined]
            )
        )
        logger.info(
            "Solution %s: deleted %d stale %s row(s)",
            sid,
            len(stale),
            model.__tablename__,  # type: ignore[attr-defined]
        )
        return len(stale)
