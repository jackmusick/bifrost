"""
Customer Rename: Get Rename Plan

Read-only planner for reconciling customer names across Bifrost-integrated
platforms using AutoTask as the source of truth.
"""

from __future__ import annotations

from typing import Any

from bifrost import integrations, organizations, workflow
from bifrost.client import get_client as get_bifrost_client
from modules.autotask import AutotaskClient, get_client as get_autotask_client
from modules.dattosaasprotection import (
    DattoSaaSProtectionClient,
    get_client as get_dattosaasprotection_client,
)
from modules.dnsfilter import DNSFilterClient, get_client as get_dnsfilter_client
from modules.vipre import get_client as get_vipre_client


# Start with the systems we can safely update in-source today.
RENAME_READY_SYSTEMS = {
    "Autotask",
    "Bifrost",
    "NinjaOne",
    "Meraki",
    "Cove Data Protection",
    "Datto RMM",
    "HaloPSA",
    "Huntress",
    "DNSFilter",
    "ConnectSecure",
    "Pax8",
}

# These integrations may be linked for access or tenant context, but they are
# not customer-name authorities for this workflow and should not generate
# rename work items.
NON_RENAME_SYSTEMS = {
    "CIPP",
    "IT Glue",
    "Microsoft",
    "Microsoft CSP",
}

# Customer-bearing systems that may contain the customer even when no mapping
# exists in Bifrost. These should be called out in the ticket for follow-up.
AUDIT_FOLLOW_UP_SYSTEMS: dict[str, str] = {
    "Datto Networking": "Audit for unmanaged presence. Current repo surface is read-only.",
    "DNSFilter": "Audit for unmanaged presence. Network inventory exists, but no validated rename path is implemented.",
}


def _normalize_match_text(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch.lower() for ch in value if ch.isalnum())


async def _audit_dattosaas_presence(
    *,
    current_name: str,
    desired_name: str,
    organization_name: str,
) -> dict[str, str]:
    candidates = {
        item
        for item in (
            current_name,
            desired_name,
            organization_name,
        )
        if isinstance(item, str) and item.strip()
    }
    normalized_candidates = {_normalize_match_text(item) for item in candidates if _normalize_match_text(item)}

    try:
        client = await get_dattosaasprotection_client(scope="global")
    except Exception as exc:
        return {
            "system": "Datto SaaS Protection",
            "note": f"Audit could not be completed automatically: {exc}",
        }

    try:
        try:
            domains = await client.list_domains()
        except Exception as exc:
            return {
                "system": "Datto SaaS Protection",
                "note": f"Audit could not be completed automatically: {exc}",
            }
    finally:
        await client.close()

    matches: list[dict[str, str | None]] = []
    for domain in domains:
        normalized = DattoSaaSProtectionClient.normalize_domain(domain)
        haystacks = {
            _normalize_match_text(normalized.get("customer_name")),
            _normalize_match_text(normalized.get("protected_domain")),
            _normalize_match_text(normalized.get("label")),
        }
        haystacks.discard("")
        if normalized_candidates.intersection(haystacks):
            matches.append(normalized)

    if not matches:
        return {
            "system": "Datto SaaS Protection",
            "note": "Checked protected customer/domain inventory; no obvious match found.",
        }

    labels = ", ".join(
        filter(
            None,
            [match.get("label") or match.get("customer_name") or match.get("id") for match in matches[:3]],
        )
    )
    suffix = " (manual review recommended; current repo surface is read-only)."
    if len(matches) == 1:
        return {
            "system": "Datto SaaS Protection",
            "note": f"Potential protected customer match found: {labels}{suffix}",
        }
    return {
        "system": "Datto SaaS Protection",
        "note": f"Potential protected customer matches found: {labels}{suffix}",
    }


async def _audit_vipre_presence() -> dict[str, str]:
    try:
        client = await get_vipre_client(scope="global")
    except Exception as exc:
        return {
            "system": "VIPRE",
            "note": f"Audit could not be completed automatically: {exc}",
        }

    try:
        try:
            sites = await client.infer_sites_from_devices()
        except Exception as exc:
            return {
                "system": "VIPRE",
                "note": f"Audit could not be completed automatically: {exc}",
            }
    finally:
        await client.close()

    matches = [
        site for site in sites
        if "findlingpark" in str(site.get("name") or "").lower()
    ]
    if not matches:
        return {
            "system": "VIPRE",
            "note": "Checked inferred site inventory; no obvious site footprint found.",
        }

    site = matches[0]
    return {
        "system": "VIPRE",
        "note": (
            "VIPRE footprint found via inferred site host "
            f"{site.get('name')} (siteUuid {site.get('id')}). "
            "Manual review required; no validated site rename path is implemented."
        ),
    }


async def _list_integration_names() -> list[str]:
    client = get_bifrost_client()
    response = await client.get("/api/integrations")
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items", []) if isinstance(payload, dict) else []

    names: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return sorted(set(names))


def _normalize_filter(values: list[str] | None) -> set[str] | None:
    if not values:
        return None
    normalized = {value.strip().lower() for value in values if isinstance(value, str) and value.strip()}
    return normalized or None


def _ticket_preview(
    *,
    company_name: str,
    desired_name: str,
    organization_name: str,
    change_reason: str | None,
    systems: list[dict[str, Any]],
    audit_follow_up: list[dict[str, str]] | None = None,
) -> dict[str, str]:
    unsupported = [item["system"] for item in systems if item["status"] != "ready"]
    title = f"Customer rename: {company_name} -> {desired_name}"

    lines = [
        "Bifrost automation rename plan",
        "",
        f"AutoTask company: {company_name}",
        f"Desired name: {desired_name}",
        f"Bifrost organization: {organization_name}",
    ]
    if change_reason:
        lines.extend(["", f"Reason: {change_reason}"])
    if unsupported:
        lines.extend(["", "Manual follow-up likely required for:"])
        for item in systems:
            if item["status"] == "ready":
                continue
            detail_parts: list[str] = []
            if item.get("current_name"):
                detail_parts.append(str(item["current_name"]))
            if item.get("entity_id"):
                detail_parts.append(f"id {item['entity_id']}")
            mapping_config = item.get("mapping_config") or {}
            if mapping_config.get("organization_id"):
                detail_parts.append(f"org {mapping_config['organization_id']}")
            detail_text = ", ".join(detail_parts)
            note_text = "; ".join(item.get("notes") or [])
            suffix_parts = [part for part in [detail_text, note_text] if part]
            suffix = f": {'; '.join(suffix_parts)}" if suffix_parts else ""
            lines.append(f"- {item['system']}{suffix}")
    if audit_follow_up:
        lines.extend(["", "Audit recommended for potentially unmanaged presence:"])
        lines.extend([f"- {item['system']}: {item['note']}" for item in audit_follow_up])

    return {
        "title": title,
        "description": "\n".join(lines),
    }


def _classify_system(*, system: str, current_name: str | None, target_name: str) -> tuple[str, list[str], bool]:
    notes: list[str] = []
    needs_change = bool(target_name and current_name != target_name)

    if system in RENAME_READY_SYSTEMS:
        if needs_change:
            if system == "Autotask":
                notes.append("Rename can be executed directly in AutoTask.")
            elif system == "NinjaOne":
                notes.append("Rename can be executed directly in NinjaOne.")
            elif system == "Meraki":
                notes.append("Rename can be executed directly in Meraki.")
            elif system == "Cove Data Protection":
                notes.append("Rename can be executed directly in Cove Data Protection.")
            elif system == "Datto RMM":
                notes.append("Rename can be executed directly in Datto RMM.")
            elif system == "HaloPSA":
                notes.append("Rename can be executed directly in HaloPSA.")
            elif system == "Huntress":
                notes.append("Rename can be executed directly in Huntress.")
            elif system == "DNSFilter":
                notes.append("Rename can be executed directly in DNSFilter.")
            elif system == "ConnectSecure":
                notes.append("Rename can be executed directly in ConnectSecure.")
            elif system == "Pax8":
                notes.append("Rename can be executed directly in Pax8.")
            else:
                notes.append("Rename can be executed directly in Bifrost.")
        else:
            notes.append("Current name already matches the target name.")
        return "ready", notes, needs_change

    if needs_change:
        notes.append("Mapping exists, but a rename adapter is not implemented yet.")
    else:
        notes.append("Current mapped name already matches the target name.")
    return "unsupported", notes, needs_change


def _build_system_entry(
    *,
    system: str,
    mapping_id: str | None,
    entity_id: str | None,
    current_name: str | None,
    target_name: str,
    status: str,
    needs_change: bool,
    notes: list[str],
    mapping_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = dict(mapping_config or {})
    safe_config: dict[str, Any] | None = None
    if system == "DNSFilter":
        network_ids = config.get("network_ids")
        if isinstance(network_ids, list) and network_ids:
            safe_config = {"network_ids": [str(item) for item in network_ids]}
            notes = [
                *notes,
                f"Mapped DNSFilter organization currently contains {len(network_ids)} network{'s' if len(network_ids) != 1 else ''}.",
            ]
        network_actions = config.get("network_actions")
        if isinstance(network_actions, list):
            safe_config = safe_config or {}
            safe_config["network_actions"] = [
                {
                    "network_id": str(item.get("network_id")),
                    "current_name": str(item.get("current_name") or ""),
                    "target_name": str(item.get("target_name") or ""),
                    "needs_change": bool(item.get("needs_change")),
                }
                for item in network_actions
                if isinstance(item, dict) and item.get("network_id") is not None
            ]

    return {
        "system": system,
        "mapping_id": mapping_id,
        "entity_id": entity_id,
        "current_name": current_name,
        "target_name": target_name,
        "status": status,
        "needs_change": needs_change,
        "notes": notes,
        "mapping_config": safe_config,
    }


async def _resolve_org_and_company(
    *,
    organization_id: str | None,
    autotask_company_id: str | None,
) -> tuple[Any, Any]:
    if organization_id:
        org = await organizations.get(organization_id)
        mapping = await integrations.get_mapping("Autotask", scope=org.id)
        if not mapping:
            raise RuntimeError(
                f"Organization {org.id} is not mapped to the Autotask integration."
            )
        return org, mapping

    if not autotask_company_id:
        raise RuntimeError("Provide organization_id or autotask_company_id.")

    mapping = await integrations.get_mapping("Autotask", entity_id=autotask_company_id)
    if not mapping or not mapping.organization_id:
        raise RuntimeError(
            f"Autotask company {autotask_company_id} is not mapped to a Bifrost organization."
        )

    org = await organizations.get(mapping.organization_id)
    return org, mapping


async def _build_dnsfilter_network_actions(
    *,
    scope: str,
    current_organization_name: str,
    target_organization_name: str,
    network_ids: list[str],
) -> list[dict[str, Any]]:
    if not network_ids:
        return []

    client = await get_dnsfilter_client(scope=scope)
    try:
        network_actions: list[dict[str, Any]] = []
        for network_id in network_ids:
            network = await client.get_network(str(network_id))
            normalized = DNSFilterClient.normalize_network(network)
            current_name = normalized["name"] or str(network_id)
            target_name = DNSFilterClient.derive_network_target_name(
                current_network_name=current_name,
                current_organization_name=current_organization_name,
                target_organization_name=target_organization_name,
            )
            network_actions.append(
                {
                    "network_id": str(network_id),
                    "current_name": current_name,
                    "target_name": target_name,
                    "needs_change": current_name != target_name,
                }
            )
        return network_actions
    finally:
        await client.close()


@workflow(
    name="Customer Rename: Get Rename Plan",
    description="Build a dry-run rename plan using AutoTask as the source of truth.",
    category="Customer Rename",
    tags=["customer-rename", "autotask", "dry-run"],
)
async def get_customer_rename_plan(
    organization_id: str | None = None,
    autotask_company_id: str | None = None,
    desired_name: str | None = None,
    desired_name_override: str | None = None,
    change_reason: str | None = None,
    systems_include: list[str] | None = None,
    systems_exclude: list[str] | None = None,
    create_ticket_preview: bool = True,
) -> dict[str, Any]:
    include_filter = _normalize_filter(systems_include)
    exclude_filter = _normalize_filter(systems_exclude) or set()

    org, autotask_mapping = await _resolve_org_and_company(
        organization_id=organization_id,
        autotask_company_id=autotask_company_id,
    )

    client = await get_autotask_client(scope=org.id)
    try:
        company = await client.get_company(autotask_mapping.entity_id)
    finally:
        await client.close()

    normalized_company = AutotaskClient.normalize_company(company)
    current_autotask_name = normalized_company["name"] or str(autotask_mapping.entity_name or "")
    resolved_desired_name = (desired_name or desired_name_override or current_autotask_name).strip()
    if not resolved_desired_name:
        raise RuntimeError("Unable to determine a desired name from AutoTask or desired_name.")

    systems: list[dict[str, Any]] = []

    autotask_status, autotask_notes, autotask_needs_change = _classify_system(
        system="Autotask",
        current_name=current_autotask_name,
        target_name=resolved_desired_name,
    )
    systems.append(
        _build_system_entry(
            system="Autotask",
            mapping_id=autotask_mapping.id,
            entity_id=str(autotask_mapping.entity_id),
            current_name=current_autotask_name,
            target_name=resolved_desired_name,
            status=autotask_status,
            needs_change=autotask_needs_change,
            notes=autotask_notes,
        )
    )

    bifrost_status, bifrost_notes, bifrost_needs_change = _classify_system(
        system="Bifrost",
        current_name=org.name,
        target_name=resolved_desired_name,
    )
    systems.append(
        _build_system_entry(
            system="Bifrost",
            mapping_id=None,
            entity_id=org.id,
            current_name=org.name,
            target_name=resolved_desired_name,
            status=bifrost_status,
            needs_change=bifrost_needs_change,
            notes=bifrost_notes,
        )
    )

    integration_names = await _list_integration_names()
    for integration_name in integration_names:
        normalized_name = integration_name.lower()
        if normalized_name == "autotask":
            continue
        if integration_name in NON_RENAME_SYSTEMS:
            continue
        if include_filter is not None and normalized_name not in include_filter:
            continue
        if normalized_name in exclude_filter:
            continue

        mapping = await integrations.get_mapping(integration_name, scope=org.id)
        if not mapping:
            continue

        status, notes, needs_change = _classify_system(
            system=integration_name,
            current_name=mapping.entity_name,
            target_name=resolved_desired_name,
        )
        safe_mapping_config = getattr(mapping, "config", None)
        child_actions = None
        if integration_name == "DNSFilter":
            network_ids = []
            if isinstance(safe_mapping_config, dict):
                maybe_network_ids = safe_mapping_config.get("network_ids")
                if isinstance(maybe_network_ids, list):
                    network_ids = [str(item) for item in maybe_network_ids if item]
            child_actions = await _build_dnsfilter_network_actions(
                scope=org.id,
                current_organization_name=str(mapping.entity_name or ""),
                target_organization_name=resolved_desired_name,
                network_ids=network_ids,
            )
            if child_actions:
                renameable_networks = [item for item in child_actions if item["needs_change"]]
                notes = [
                    *notes,
                    (
                        f"{len(renameable_networks)} DNSFilter network"
                        f"{'s' if len(renameable_networks) != 1 else ''} will also be renamed."
                    ),
                ]
        systems.append(
            _build_system_entry(
                system=integration_name,
                mapping_id=mapping.id,
                entity_id=mapping.entity_id,
                current_name=mapping.entity_name,
                target_name=resolved_desired_name,
                status=status,
                needs_change=needs_change,
                notes=notes,
                mapping_config=(
                    {
                        **(safe_mapping_config or {}),
                        "network_actions": child_actions,
                    }
                    if integration_name == "DNSFilter" and child_actions is not None
                    else safe_mapping_config
                ),
            )
        )

    audit_follow_up = [
        {"system": name, "note": note}
        for name, note in AUDIT_FOLLOW_UP_SYSTEMS.items()
        if not any(item["system"] == name for item in systems)
    ]
    if not any(item["system"] == "Datto SaaS Protection" for item in systems):
        audit_follow_up.insert(
            0,
            await _audit_dattosaas_presence(
                current_name=current_autotask_name,
                desired_name=resolved_desired_name,
                organization_name=org.name,
            ),
        )
    if not any(item["system"] == "VIPRE" for item in systems):
        insert_at = 1 if audit_follow_up and audit_follow_up[0]["system"] == "Datto SaaS Protection" else 0
        audit_follow_up.insert(insert_at, await _audit_vipre_presence())

    ticket_preview = (
        None
        if not create_ticket_preview
        else _ticket_preview(
            company_name=current_autotask_name,
            desired_name=resolved_desired_name,
            organization_name=org.name,
            change_reason=change_reason,
            systems=systems,
            audit_follow_up=audit_follow_up,
        )
    )

    return {
        "organization": {
            "id": org.id,
            "name": org.name,
        },
        "autotask": {
            "company_id": str(autotask_mapping.entity_id),
            "current_name": current_autotask_name,
            "desired_name": resolved_desired_name,
            "needs_update": current_autotask_name != resolved_desired_name,
            "mapping_id": autotask_mapping.id,
        },
        "change_reason": change_reason,
        "systems": systems,
        "audit_follow_up": audit_follow_up,
        "ticket_preview": ticket_preview,
    }
