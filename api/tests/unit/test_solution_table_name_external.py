"""
NEW-3 failing-first proof: _resolve_solution_table_by_name gated the
``or_(org == target, org IS NULL)`` arm only on ``is_superuser``, so an
external (non-bypass) principal could resolve a GLOBAL solution-managed table
by name. The global arm must be dropped for externals.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.routers.tables import _resolve_solution_table_by_name


def _ctx(*, is_superuser=False, is_external=False, app_id=None, solution_id=None):
    db = AsyncMock()
    db.execute = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=uuid4())  # solution_id lookup
    db.execute.return_value = result
    user = SimpleNamespace(is_superuser=is_superuser, is_external=is_external)
    return SimpleNamespace(db=db, user=user, app_id=app_id, solution_id=solution_id)


def _last_sql(ctx) -> str:
    stmt = ctx.db.execute.await_args_list[-1].args[0]
    full = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    _, _, where = full.partition("WHERE")
    return where


@pytest.mark.asyncio
class TestResolveSolutionTableExternal:
    async def test_external_drops_global_arm(self):
        target = uuid4()
        ctx = _ctx(is_external=True, solution_id=str(uuid4()))
        await _resolve_solution_table_by_name(ctx, "tbl", target)
        sql = _last_sql(ctx)
        assert "tables.organization_id IS NULL" not in sql

    async def test_regular_user_keeps_global_arm(self):
        target = uuid4()
        ctx = _ctx(is_external=False, solution_id=str(uuid4()))
        await _resolve_solution_table_by_name(ctx, "tbl", target)
        sql = _last_sql(ctx)
        assert "tables.organization_id IS NULL" in sql

    async def test_superuser_unscoped(self):
        target = uuid4()
        ctx = _ctx(is_superuser=True, solution_id=str(uuid4()))
        await _resolve_solution_table_by_name(ctx, "tbl", target)
        sql = _last_sql(ctx)
        assert "tables.organization_id" not in sql
