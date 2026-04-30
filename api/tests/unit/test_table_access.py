"""Unit tests for the table access checker."""
from __future__ import annotations

from uuid import uuid4

import pytest

from shared.table_access import (
    Action,
    Caller,
    CheckResult,  # noqa: F401
    WorkflowCaller,
    check_table_access,
)


def _table_access(**overrides):
    base = {
        "everyone": {"read": False, "create": False, "update": False, "delete": False},
        "role": {"roles": [], "read": False, "create": False, "update": False, "delete": False},
        "creator": {"read": False, "create": False, "update": False, "delete": False},
    }
    for scope, flags in overrides.items():
        base[scope] = {**base[scope], **flags}
    return base


def _user(user_id=None, role_ids=None, is_admin=False):
    return Caller(
        user_id=user_id or uuid4(),
        role_ids=set(role_ids or []),
        is_admin=is_admin,
    )


# ---- Admin and workflow always allow ----------------------------------------

@pytest.mark.parametrize("action", list(Action))
def test_admin_allowed_for_every_action_even_with_no_access(action):
    res = check_table_access(action=action, access=None, caller=_user(is_admin=True))
    assert res.allow is True


@pytest.mark.parametrize("action", list(Action))
def test_workflow_caller_allowed_even_with_no_access(action):
    res = check_table_access(action=action, access=None, caller=WorkflowCaller())
    assert res.allow is True


# ---- Default deny ------------------------------------------------------------

@pytest.mark.parametrize("action", list(Action))
def test_no_access_block_denies_non_admin(action):
    res = check_table_access(action=action, access=None, caller=_user())
    assert res.allow is False


@pytest.mark.parametrize("action", list(Action))
def test_empty_access_block_denies_non_admin(action):
    res = check_table_access(action=action, access=_table_access(), caller=_user())
    assert res.allow is False


# ---- Everyone scope ---------------------------------------------------------

@pytest.mark.parametrize("action", list(Action))
def test_everyone_grant_allows(action):
    access = _table_access(everyone={action.value: True})
    res = check_table_access(action=action, access=access, caller=_user())
    assert res.allow is True


# ---- Role scope -------------------------------------------------------------

def test_role_grant_requires_membership():
    role = uuid4()
    access = _table_access(role={"roles": [str(role)], "read": True})
    member = _user(role_ids=[role])
    non_member = _user(role_ids=[])
    assert check_table_access(action=Action.READ, access=access, caller=member).allow is True
    assert check_table_access(action=Action.READ, access=access, caller=non_member).allow is False


# ---- Creator scope ----------------------------------------------------------

def test_creator_grant_only_applies_to_owned_rows():
    user = uuid4()
    access = _table_access(creator={"read": True, "update": True, "delete": True})
    owner = _user(user_id=user)
    assert check_table_access(
        action=Action.READ, access=access, caller=owner, row_created_by=user
    ).allow is True
    assert check_table_access(
        action=Action.READ, access=access, caller=owner, row_created_by=uuid4()
    ).allow is False


def test_creator_create_grants_insert():
    access = _table_access(creator={"create": True})
    res = check_table_access(action=Action.CREATE, access=access, caller=_user(), row_created_by=None)
    assert res.allow is True


# ---- Additive resolution ----------------------------------------------------

def test_union_of_grants():
    role = uuid4()
    access = _table_access(
        everyone={"read": True},
        role={"roles": [str(role)], "update": True},
        creator={"delete": True},
    )
    user_id = uuid4()
    caller = _user(user_id=user_id, role_ids=[role])
    assert check_table_access(action=Action.READ, access=access, caller=caller).allow is True
    assert check_table_access(action=Action.UPDATE, access=access, caller=caller, row_created_by=uuid4()).allow is True
    assert check_table_access(
        action=Action.DELETE, access=access, caller=caller, row_created_by=user_id
    ).allow is True


# ---- List/query Creator filter signal ---------------------------------------

def test_list_filter_signal_creator_only():
    access = _table_access(creator={"read": True})
    res = check_table_access(action=Action.READ, access=access, caller=_user(), row_created_by=None)
    # No row supplied = list/query mode
    assert res.allow is True
    assert res.creator_filter_required is True


def test_list_filter_signal_everyone_overrides_creator():
    access = _table_access(everyone={"read": True}, creator={"read": True})
    res = check_table_access(action=Action.READ, access=access, caller=_user(), row_created_by=None)
    assert res.allow is True
    assert res.creator_filter_required is False
