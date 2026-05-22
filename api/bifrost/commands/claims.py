"""CLI commands for managing custom claims."""

from __future__ import annotations

from typing import Any

import click

from bifrost.client import BifrostClient
from bifrost.contracts import CustomClaimCreate, CustomClaimUpdate
from bifrost.dto_flags import (
    DTO_EXCLUDES,
    DTO_REF_LOOKUPS,
    assemble_body,
    build_cli_flags,
)
from bifrost.refs import RefResolver

from .base import _apply_flags, entity_group, output_result, pass_resolver, run_async

claims_group = entity_group("claims", "Manage custom claims.")


_CREATE_FLAGS = build_cli_flags(
    CustomClaimCreate,
    exclude=DTO_EXCLUDES.get("CustomClaimCreate", set()),
    verb_ref_lookups=DTO_REF_LOOKUPS.get("CustomClaimCreate", {}),
)

_UPDATE_FLAGS = build_cli_flags(
    CustomClaimUpdate,
    exclude=DTO_EXCLUDES.get("CustomClaimUpdate", set()),
    verb_ref_lookups=DTO_REF_LOOKUPS.get("CustomClaimUpdate", {}),
)


@claims_group.command("list")
@click.pass_context
@pass_resolver
@run_async
async def list_claims(
    ctx: click.Context,
    *,
    client: BifrostClient,
    resolver: RefResolver,  # noqa: ARG001 - kept for signature parity
) -> None:
    """List custom claims for the current org."""
    response = await client.get("/api/claims")
    response.raise_for_status()
    output_result(response.json(), ctx=ctx)


@claims_group.command("get")
@click.argument("name")
@click.pass_context
@pass_resolver
@run_async
async def get_claim(
    ctx: click.Context,
    name: str,
    *,
    client: BifrostClient,
    resolver: RefResolver,  # noqa: ARG001 - kept for signature parity
) -> None:
    """Get a custom claim by name."""
    response = await client.get(f"/api/claims/{name}")
    response.raise_for_status()
    output_result(response.json(), ctx=ctx)


@claims_group.command("create")
@_apply_flags(_CREATE_FLAGS)
@click.pass_context
@pass_resolver
@run_async
async def create_claim(
    ctx: click.Context,
    *,
    client: BifrostClient,
    resolver: RefResolver,
    **fields: Any,
) -> None:
    """Create a custom claim."""
    body = await assemble_body(CustomClaimCreate, fields, resolver=resolver)
    response = await client.post("/api/claims", json=body)
    response.raise_for_status()
    output_result(response.json(), ctx=ctx)


@claims_group.command("update")
@click.argument("name")
@_apply_flags(_UPDATE_FLAGS)
@click.pass_context
@pass_resolver
@run_async
async def update_claim(
    ctx: click.Context,
    name: str,
    *,
    client: BifrostClient,
    resolver: RefResolver,
    **fields: Any,
) -> None:
    """Update a custom claim by name."""
    body = await assemble_body(CustomClaimUpdate, fields, resolver=resolver)
    response = await client.patch(f"/api/claims/{name}", json=body)
    response.raise_for_status()
    output_result(response.json(), ctx=ctx)


@claims_group.command("delete")
@click.argument("name")
@click.pass_context
@pass_resolver
@run_async
async def delete_claim(
    ctx: click.Context,
    name: str,
    *,
    client: BifrostClient,
    resolver: RefResolver,  # noqa: ARG001 - kept for signature parity
) -> None:
    """Delete a custom claim by name."""
    response = await client.delete(f"/api/claims/{name}")
    response.raise_for_status()
    output_result({"deleted": name}, ctx=ctx)


__all__ = ["claims_group"]
