"""CLI commands for managing workflows.

Implements Task 5c of the CLI mutation surface plan:

* ``bifrost workflows list`` → ``GET /api/workflows``
* ``bifrost workflows register`` → ``POST /api/workflows/register`` (registers
  a decorated function from an existing workspace ``.py`` file).
* ``bifrost workflows update <ref>`` → ``PATCH /api/workflows/{uuid}`` (body
  from :class:`WorkflowUpdateRequest`).
* ``bifrost workflows delete <ref>`` → ``DELETE /api/workflows/{uuid}``
  (forwards ``--force`` as ``force_deactivation`` on the request body).
* ``bifrost workflows grant-role <ref> <role-ref>`` →
  ``POST /api/workflows/{uuid}/roles`` with a single-element role_ids list.
* ``bifrost workflows revoke-role <ref> <role-ref>`` →
  ``DELETE /api/workflows/{uuid}/roles/{role_uuid}``.

Ref resolution uses :class:`RefResolver`:
- ``workflow`` refs accept UUID, name, or ``path::func``.
- ``role`` refs accept UUID or name.

DTO-driven flags for ``update`` are generated from
:class:`WorkflowUpdateRequest` via :func:`build_cli_flags` with the exclude
list in :data:`DTO_EXCLUDES` (UI / code-defined fields that intentionally do
not surface on the CLI — see the plan's cross-cutting exclusion rationale).

Partial-failure handling (plan open Q #3): ``grant-role`` and ``revoke-role``
each act on a single role per invocation. Failures surface via the standard
HTTP error path (exit 1 with the server body on stderr). A future
``update --roles foo,bar,baz`` diff-and-apply command can reuse this
contract by iterating role refs and aggregating per-role outcomes.
"""

from __future__ import annotations

from typing import Any

import click

from bifrost.client import BifrostClient
from bifrost.dto_flags import (
    DTO_EXCLUDES,
    DTO_REF_LOOKUPS,
    assemble_body,
    build_cli_flags,
)
from bifrost.refs import RefResolver
from src.models.contracts.workflows import WorkflowUpdateRequest

from .base import _apply_flags, entity_group, output_result, pass_resolver, run_async

workflows_group = entity_group("workflows", "Manage workflows.")


_UPDATE_FLAGS = build_cli_flags(
    WorkflowUpdateRequest,
    exclude=DTO_EXCLUDES.get("WorkflowUpdateRequest", set()),
    verb_ref_lookups=DTO_REF_LOOKUPS.get("WorkflowUpdateRequest", {}),
)


@workflows_group.command("list")
@click.pass_context
@pass_resolver
@run_async
async def list_workflows(
    ctx: click.Context,
    *,
    client: BifrostClient,
    resolver: RefResolver,  # noqa: ARG001 - kept for signature parity
) -> None:
    """List all workflows visible to the caller."""
    response = await client.get("/api/workflows")
    response.raise_for_status()
    output_result(response.json(), ctx=ctx)


@workflows_group.command("register")
@click.option(
    "--path",
    "path",
    required=True,
    type=str,
    help="Workspace-relative path to the .py file containing the decorated function.",
)
@click.option(
    "--function-name",
    "function_name",
    required=True,
    type=str,
    help="Name of the decorated function to register.",
)
@click.option(
    "--org",
    "organization_id",
    type=str,
    default=None,
    help="Organization ref (UUID or name) to scope the workflow to; omit for global.",
)
@click.pass_context
@pass_resolver
@run_async
async def register_workflow(
    ctx: click.Context,
    *,
    client: BifrostClient,
    resolver: RefResolver,
    path: str,
    function_name: str,
    organization_id: str | None,
) -> None:
    """Register a decorated function from an existing workspace ``.py`` file.

    The file must already exist in the workspace (written via ``bifrost push``
    or the file editor). This command indexes a ``@workflow`` / ``@tool`` /
    ``@data_provider`` function so it becomes executable via the API.
    """
    body: dict[str, Any] = {"path": path, "function_name": function_name}
    if organization_id is not None:
        body["organization_id"] = await resolver.resolve("org", organization_id)
    response = await client.post("/api/workflows/register", json=body)
    response.raise_for_status()
    output_result(response.json(), ctx=ctx)


@workflows_group.command("update")
@click.argument("ref")
@_apply_flags(_UPDATE_FLAGS)
@click.pass_context
@pass_resolver
@run_async
async def update_workflow(
    ctx: click.Context,
    ref: str,
    *,
    client: BifrostClient,
    resolver: RefResolver,
    **fields: Any,
) -> None:
    """Update a workflow's editable properties.

    ``REF`` is a UUID, workflow name, or ``path::func`` locator. See
    :mod:`bifrost.refs` for resolution rules.
    """
    workflow_uuid = await resolver.resolve("workflow", ref)
    body = await assemble_body(WorkflowUpdateRequest, fields, resolver=resolver)
    response = await client.patch(
        f"/api/workflows/{workflow_uuid}", json=body
    )
    response.raise_for_status()
    output_result(response.json(), ctx=ctx)


@workflows_group.command("delete")
@click.argument("ref")
@click.option(
    "--force/--no-force",
    "force",
    default=False,
    help=(
        "Skip the deactivation protection check and delete the workflow even "
        "if it has dependent forms/apps/agents."
    ),
)
@click.pass_context
@pass_resolver
@run_async
async def delete_workflow(
    ctx: click.Context,
    ref: str,
    *,
    client: BifrostClient,
    resolver: RefResolver,
    force: bool,
) -> None:
    """Delete a workflow by removing its function from the source file.

    ``REF`` is a UUID, workflow name, or ``path::func`` locator. Without
    ``--force``, the API performs a deactivation-protection pre-check and
    returns 409 if the workflow has dependents; pass ``--force`` to bypass.
    """
    workflow_uuid = await resolver.resolve("workflow", ref)
    if force:
        # httpx's AsyncClient.delete does not accept a json body; use the
        # generic request() helper so force_deactivation can reach the server.
        response = await client.request(
            "DELETE",
            f"/api/workflows/{workflow_uuid}",
            json={"force_deactivation": True},
        )
    else:
        response = await client.delete(f"/api/workflows/{workflow_uuid}")
    response.raise_for_status()
    output_result(response.json(), ctx=ctx)


@workflows_group.command("grant-role")
@click.argument("ref")
@click.argument("role_ref")
@click.pass_context
@pass_resolver
@run_async
async def grant_role(
    ctx: click.Context,
    ref: str,
    role_ref: str,
    *,
    client: BifrostClient,
    resolver: RefResolver,
) -> None:
    """Grant a role access to a workflow.

    ``REF`` is a workflow UUID / name / ``path::func``. ``ROLE_REF`` is a
    role UUID or role name. The underlying endpoint accepts a batch of
    role IDs — this command sends a single-element list for simplicity.
    """
    workflow_uuid = await resolver.resolve("workflow", ref)
    role_uuid = await resolver.resolve("role", role_ref)
    response = await client.post(
        f"/api/workflows/{workflow_uuid}/roles",
        json={"role_ids": [role_uuid]},
    )
    response.raise_for_status()
    output_result(
        {"workflow_id": workflow_uuid, "role_id": role_uuid, "granted": True},
        ctx=ctx,
    )


@workflows_group.command("revoke-role")
@click.argument("ref")
@click.argument("role_ref")
@click.pass_context
@pass_resolver
@run_async
async def revoke_role(
    ctx: click.Context,
    ref: str,
    role_ref: str,
    *,
    client: BifrostClient,
    resolver: RefResolver,
) -> None:
    """Revoke a role's access from a workflow.

    ``REF`` is a workflow UUID / name / ``path::func``. ``ROLE_REF`` is a
    role UUID or role name.
    """
    workflow_uuid = await resolver.resolve("workflow", ref)
    role_uuid = await resolver.resolve("role", role_ref)
    response = await client.delete(
        f"/api/workflows/{workflow_uuid}/roles/{role_uuid}",
    )
    response.raise_for_status()
    output_result(
        {"workflow_id": workflow_uuid, "role_id": role_uuid, "revoked": True},
        ctx=ctx,
    )


__all__ = ["workflows_group"]
