"""EXT-1 NEW-J: an org-less EXTERNAL principal must read NOTHING, never the
GLOBAL tier.

Root cause: ``column == filter_org`` compiles to ``IS NULL`` when an external
principal's ``organization_id`` is None, so the hand-rolled "external -> own org
only" inline gates leaked all global (org IS NULL) entities to a MISCONFIGURED
org-less external. The canonical fix is at the source: ``resolve_org_filter``
returns the ``OrgFilterType.EMPTY`` sentinel for an org-less external, and the
shared ``org_filter_clause`` helper compiles it to ``false()``.

These tests pin:
- resolve_org_filter: org-less external -> EMPTY; org-having external -> ORG_ONLY
  (own org); normal user -> ORG_PLUS_GLOBAL; superuser -> ALL.
- org_filter_clause: EMPTY -> false(); ORG_ONLY/ORG_PLUS_GLOBAL with a None org
  collapse to a no-match (never IS NULL); the normal forms still compile right.
"""

from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy import Column, MetaData, Table, Uuid

from src.core.org_filter import (
    OrgFilterType,
    org_filter_clause,
    resolve_org_filter,
)

_md = MetaData()
_t = Table("t", _md, Column("organization_id", Uuid, nullable=True))
ORG_COL = _t.c.organization_id


def _sql(clause) -> str:
    if clause is None:
        return "<none>"
    return str(clause.compile(compile_kwargs={"literal_binds": True}))


def _user(*, is_external, is_superuser=False, org=...):
    u = MagicMock()
    u.is_superuser = is_superuser
    u.is_external = is_external
    u.organization_id = uuid4() if org is ... else org
    return u


class TestResolveOrgFilterEmptySentinel:
    def test_orgless_external_is_empty(self):
        ft, org = resolve_org_filter(_user(is_external=True, org=None))
        assert ft is OrgFilterType.EMPTY
        assert org is None

    def test_org_having_external_is_org_only(self):
        org_id = uuid4()
        ft, org = resolve_org_filter(_user(is_external=True, org=org_id))
        assert ft is OrgFilterType.ORG_ONLY
        assert org == org_id

    def test_normal_user_is_org_plus_global(self):
        ft, _ = resolve_org_filter(_user(is_external=False))
        assert ft is OrgFilterType.ORG_PLUS_GLOBAL

    def test_orgless_normal_user_is_global_only_unchanged(self):
        # Non-external org-less user keeps the existing GLOBAL_ONLY edge case —
        # NEW-J only changes the EXTERNAL org-less case.
        ft, _ = resolve_org_filter(_user(is_external=False, org=None))
        assert ft is OrgFilterType.GLOBAL_ONLY

    def test_superuser_unaffected(self):
        ft, _ = resolve_org_filter(
            _user(is_external=True, is_superuser=True)
        )
        assert ft is OrgFilterType.ALL


class TestOrgFilterClause:
    def test_empty_compiles_to_false_no_isnull(self):
        sql = _sql(org_filter_clause(ORG_COL, OrgFilterType.EMPTY, None))
        assert "IS NULL" not in sql
        assert "false" in sql.lower()

    def test_all_is_none(self):
        assert org_filter_clause(ORG_COL, OrgFilterType.ALL, None) is None

    def test_org_only_with_none_collapses_to_no_match(self):
        # The NEW-J trap: ORG_ONLY + None must NOT compile to IS NULL.
        sql = _sql(org_filter_clause(ORG_COL, OrgFilterType.ORG_ONLY, None))
        assert "IS NULL" not in sql
        assert "false" in sql.lower()

    def test_org_only_with_org_filters_that_org(self):
        org_id = uuid4()
        sql = _sql(org_filter_clause(ORG_COL, OrgFilterType.ORG_ONLY, org_id))
        assert "IS NULL" not in sql
        assert str(org_id).replace("-", "") in sql.replace("-", "")

    def test_org_plus_global_with_org_unions_global(self):
        org_id = uuid4()
        sql = _sql(
            org_filter_clause(ORG_COL, OrgFilterType.ORG_PLUS_GLOBAL, org_id)
        )
        assert "IS NULL" in sql
        assert str(org_id).replace("-", "") in sql.replace("-", "")

    def test_org_plus_global_with_none_is_global_only(self):
        sql = _sql(
            org_filter_clause(ORG_COL, OrgFilterType.ORG_PLUS_GLOBAL, None)
        )
        assert "IS NULL" in sql

    def test_global_only_is_isnull(self):
        sql = _sql(org_filter_clause(ORG_COL, OrgFilterType.GLOBAL_ONLY, None))
        assert "IS NULL" in sql
