"""
Customer Rename: Execute Rename

Execute the supported portion of a customer rename plan. AutoTask remains the
source of truth; today the only direct rename action implemented here is the
Bifrost organization rename.
"""

from __future__ import annotations

from typing import Any
from bifrost import integrations, organizations, workflow
from features.autotask.workflows.create_ticket import create_autotask_ticket
from features.autotask.workflows.create_ticket_note import create_autotask_ticket_note
from features.autotask.workflows.sync_customers import sync_autotask_customers
from features.autotask.workflows.update_company import update_autotask_company
from features.connectsecure.workflows.update_company import update_connectsecure_company
from features.connectsecure.workflows.sync_companies import sync_connectsecure_companies
from features.cove.workflows.update_customer import update_cove_customer
from features.cove.workflows.sync_customers import sync_cove_customers
from features.customer_rename.workflows.get_rename_plan import get_customer_rename_plan
from features.dattormm.workflows.update_site import update_dattormm_site
from features.dattormm.workflows.sync_sites import sync_dattormm_sites
from features.dnsfilter.workflows.update_organization import update_dnsfilter_organization
from features.dnsfilter.workflows.sync_networks import sync_dnsfilter_networks
from features.halopsa.workflows.update_client import update_halopsa_client
from features.huntress.workflows.update_organization import update_huntress_organization
from features.huntress.workflows.sync_organizations import sync_huntress_organizations
from features.meraki.workflows.update_organization import update_meraki_organization
from features.meraki.workflows.sync_organizations import sync_meraki_organizations
from features.ninjaone.workflows.update_organization import update_ninjaone_organization
from features.ninjaone.workflows.sync_organizations import sync_ninjaone_organizations
from features.pax8.workflows.update_company import update_pax8_company
from features.pax8.workflows.sync_companies import sync_pax8_companies
from modules.dnsfilter import DNSFilterClient, get_client as get_dnsfilter_client


def _render_execution_note(
    *,
    desired_name: str,
    actions: list[dict[str, Any]],
    unsupported: list[dict[str, Any]],
    sync_results: list[dict[str, Any]] | None = None,
    audit_follow_up: list[dict[str, str]] | None = None,
) -> str:
    lines = [
        f"Target rename: {desired_name}",
        "",
        "Execution summary:",
    ]

    if actions:
        lines.extend(
            [
                f"- {action['system']}: {action['status']}"
                + (f" ({action['details']})" if action.get("details") else "")
                for action in actions
            ]
        )
    else:
        lines.append("- No supported rename actions were needed.")

    if unsupported:
        lines.extend(["", "Manual follow-up required for:"])
        for item in unsupported:
            detail_parts: list[str] = []
            if item.get("current_name"):
                detail_parts.append(str(item["current_name"]))
            if item.get("entity_id"):
                detail_parts.append(f"id {item['entity_id']}")
            mapping_config = item.get("mapping_config") or {}
            if mapping_config.get("organization_id"):
                detail_parts.append(f"org {mapping_config['organization_id']}")
            network_ids = mapping_config.get("network_ids")
            if isinstance(network_ids, list) and network_ids:
                detail_parts.append(
                    f"{len(network_ids)} network{'s' if len(network_ids) != 1 else ''}"
                )
            detail_text = ", ".join(detail_parts)
            note_text = "; ".join(item.get("notes") or [])
            suffix_parts = [part for part in [detail_text, note_text] if part]
            suffix = f": {'; '.join(suffix_parts)}" if suffix_parts else ""
            lines.append(f"- {item['system']}{suffix}")
    if sync_results:
        lines.extend(["", "Post-rename mapping refresh:"])
        for item in sync_results:
            detail = item.get("details")
            suffix = f" ({detail})" if detail else ""
            lines.append(f"- {item['system']}: {item['status']}{suffix}")
    if audit_follow_up:
        lines.extend(["", "Audit recommended for potentially unmanaged presence:"])
        lines.extend([f"- {item['system']}: {item['note']}" for item in audit_follow_up])

    return "\n".join(lines)


async def _refresh_mapping_name(
    *,
    organization_id: str,
    system: str,
    entity_id: str,
    entity_name: str | None,
    mapping_config: dict[str, Any] | None = None,
) -> None:
    config = None
    if system == "DNSFilter" and isinstance(mapping_config, dict):
        network_ids = mapping_config.get("network_ids")
        if isinstance(network_ids, list):
            config = {"network_ids": [str(item) for item in network_ids if item is not None]}

    await integrations.upsert_mapping(
        system,
        scope=organization_id,
        entity_id=entity_id,
        entity_name=entity_name,
        config=config,
    )


POST_RENAME_SYNC_HANDLERS = {
    "Autotask": sync_autotask_customers,
    "ConnectSecure": sync_connectsecure_companies,
    "Cove Data Protection": sync_cove_customers,
    "Datto RMM": sync_dattormm_sites,
    "DNSFilter": sync_dnsfilter_networks,
    "Huntress": sync_huntress_organizations,
    "Meraki": sync_meraki_organizations,
    "NinjaOne": sync_ninjaone_organizations,
    "Pax8": sync_pax8_companies,
}


async def _run_post_rename_syncs(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    renamed_systems = []
    for action in actions:
        if action.get("status") != "renamed":
            continue
        system = action.get("system")
        if system in POST_RENAME_SYNC_HANDLERS and system not in renamed_systems:
            renamed_systems.append(system)

    for system in renamed_systems:
        handler = POST_RENAME_SYNC_HANDLERS[system]
        try:
            result = await handler()
            details = None
            if isinstance(result, dict):
                summary_parts = []
                for key in ("mapped", "already_mapped", "created_orgs", "errors"):
                    if key not in result:
                        continue
                    value = result[key]
                    if key == "errors":
                        summary_parts.append(f"errors={len(value) if isinstance(value, list) else value}")
                    else:
                        summary_parts.append(f"{key}={value}")
                details = ", ".join(summary_parts) if summary_parts else None
            results.append(
                {
                    "system": system,
                    "status": "synced",
                    "details": details,
                    "result": result,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "system": system,
                    "status": "sync_failed",
                    "details": str(exc),
                    "result": None,
                }
            )
    return results


@workflow(
    name="Customer Rename: Execute Rename",
    description="Create a ticket and execute the supported portion of a customer rename plan.",
    category="Customer Rename",
    tags=["customer-rename", "autotask", "execution"],
)
async def execute_customer_rename(
    organization_id: str | None = None,
    autotask_company_id: str | None = None,
    desired_name: str | None = None,
    desired_name_override: str | None = None,
    change_reason: str | None = None,
    systems_include: list[str] | None = None,
    systems_exclude: list[str] | None = None,
    create_ticket: bool = True,
    refresh_mappings: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    plan = await get_customer_rename_plan(
        organization_id=organization_id,
        autotask_company_id=autotask_company_id,
        desired_name=desired_name,
        desired_name_override=desired_name_override,
        change_reason=change_reason,
        systems_include=systems_include,
        systems_exclude=systems_exclude,
        create_ticket_preview=create_ticket,
    )

    if dry_run:
        return {
            "dry_run": True,
            "plan": plan,
            "ticket": None,
            "actions": [],
        }

    desired_name = plan["autotask"]["desired_name"]
    org = plan["organization"]

    ticket = None
    if create_ticket:
        preview = plan.get("ticket_preview") or {}
        ticket_result = await create_autotask_ticket(
            company_id=plan["autotask"]["company_id"],
            title=preview.get("title") or f"Customer rename: {org['name']} -> {desired_name}",
            description=preview.get("description") or "",
        )
        ticket = ticket_result.get("ticket")

    actions: list[dict[str, Any]] = []
    forced_unsupported: list[dict[str, Any]] = []
    autotask_plan = next((item for item in plan["systems"] if item["system"] == "Autotask"), None)
    if autotask_plan and autotask_plan["needs_change"]:
        updated_company = await update_autotask_company(
            company_id=plan["autotask"]["company_id"],
            company_name=desired_name,
        )
        await _refresh_mapping_name(
            organization_id=org["id"],
            system="Autotask",
            entity_id=str(plan["autotask"]["company_id"]),
            entity_name=updated_company["company"]["name"],
        )
        actions.append(
            {
                "system": "Autotask",
                "status": "renamed",
                "details": (
                    f"{plan['autotask']['current_name']} -> "
                    f"{updated_company['company']['name']}"
                ),
                "result": updated_company["company"],
            }
        )
    else:
        actions.append(
            {
                "system": "Autotask",
                "status": "noop",
                "details": "Company name already matched the target name.",
                "result": {
                    "id": plan["autotask"]["company_id"],
                    "name": plan["autotask"]["current_name"],
                },
            }
        )

    bifrost_plan = next((item for item in plan["systems"] if item["system"] == "Bifrost"), None)
    if bifrost_plan and bifrost_plan["needs_change"]:
        updated_org = await organizations.update(org["id"], name=desired_name)
        actions.append(
            {
                "system": "Bifrost",
                "status": "renamed",
                "details": f"{org['name']} -> {updated_org.name}",
                "result": {"organization_id": updated_org.id, "name": updated_org.name},
            }
        )
    else:
        actions.append(
            {
                "system": "Bifrost",
                "status": "noop",
                "details": "Organization name already matched the target name.",
                "result": {"organization_id": org["id"], "name": org["name"]},
            }
        )

    ninjaone_plan = next((item for item in plan["systems"] if item["system"] == "NinjaOne"), None)
    if ninjaone_plan and ninjaone_plan["needs_change"]:
        updated_org = await update_ninjaone_organization(
            organization_id=str(ninjaone_plan["entity_id"]),
            name=desired_name,
        )
        await _refresh_mapping_name(
            organization_id=org["id"],
            system="NinjaOne",
            entity_id=str(ninjaone_plan["entity_id"]),
            entity_name=updated_org["organization"]["name"],
        )
        actions.append(
            {
                "system": "NinjaOne",
                "status": "renamed",
                "details": (
                    f"{ninjaone_plan['current_name']} -> "
                    f"{updated_org['organization']['name']}"
                ),
                "result": updated_org["organization"],
            }
        )
    elif ninjaone_plan:
        actions.append(
            {
                "system": "NinjaOne",
                "status": "noop",
                "details": "Organization name already matched the target name.",
                "result": {
                    "id": str(ninjaone_plan["entity_id"]),
                    "name": ninjaone_plan["current_name"],
                },
            }
        )

    meraki_plan = next((item for item in plan["systems"] if item["system"] == "Meraki"), None)
    if meraki_plan and meraki_plan["needs_change"]:
        updated_org = await update_meraki_organization(
            organization_id=str(meraki_plan["entity_id"]),
            name=desired_name,
        )
        await _refresh_mapping_name(
            organization_id=org["id"],
            system="Meraki",
            entity_id=str(meraki_plan["entity_id"]),
            entity_name=updated_org["organization"]["name"],
        )
        actions.append(
            {
                "system": "Meraki",
                "status": "renamed",
                "details": (
                    f"{meraki_plan['current_name']} -> "
                    f"{updated_org['organization']['name']}"
                ),
                "result": updated_org["organization"],
            }
        )
    elif meraki_plan:
        actions.append(
            {
                "system": "Meraki",
                "status": "noop",
                "details": "Organization name already matched the target name.",
                "result": {
                    "id": str(meraki_plan["entity_id"]),
                    "name": meraki_plan["current_name"],
                },
            }
        )

    cove_plan = next((item for item in plan["systems"] if item["system"] == "Cove Data Protection"), None)
    if cove_plan and cove_plan["needs_change"]:
        try:
            updated_customer = await update_cove_customer(
                partner_id=str(cove_plan["entity_id"]),
                name=desired_name,
            )
            await _refresh_mapping_name(
                organization_id=org["id"],
                system="Cove Data Protection",
                entity_id=str(cove_plan["entity_id"]),
                entity_name=updated_customer["customer"]["name"],
            )
            actions.append(
                {
                    "system": "Cove Data Protection",
                    "status": "renamed",
                    "details": (
                        f"{cove_plan['current_name']} -> "
                        f"{updated_customer['customer']['name']}"
                    ),
                    "result": updated_customer["customer"],
                }
            )
        except Exception as exc:
            if "Operation is restricted by user role" not in str(exc):
                raise
            forced_unsupported.append(
                {
                    **cove_plan,
                    "notes": [
                        *list(cove_plan.get("notes") or []),
                        "Cove rejected the rename because the current API user role cannot modify this customer.",
                    ],
                }
            )
            actions.append(
                {
                    "system": "Cove Data Protection",
                    "status": "manual",
                    "details": "Skipped because the current Cove API user role cannot modify this customer.",
                    "result": {
                        "id": str(cove_plan["entity_id"]),
                        "name": cove_plan["current_name"],
                    },
                }
            )
    elif cove_plan:
        actions.append(
            {
                "system": "Cove Data Protection",
                "status": "noop",
                "details": "Customer name already matched the target name.",
                "result": {
                    "id": str(cove_plan["entity_id"]),
                    "name": cove_plan["current_name"],
                },
            }
        )

    dattormm_plan = next((item for item in plan["systems"] if item["system"] == "Datto RMM"), None)
    if dattormm_plan and dattormm_plan["needs_change"]:
        updated_site = await update_dattormm_site(
            site_uid=str(dattormm_plan["entity_id"]),
            name=desired_name,
        )
        await _refresh_mapping_name(
            organization_id=org["id"],
            system="Datto RMM",
            entity_id=str(dattormm_plan["entity_id"]),
            entity_name=updated_site["site"]["name"],
        )
        actions.append(
            {
                "system": "Datto RMM",
                "status": "renamed",
                "details": (
                    f"{dattormm_plan['current_name']} -> "
                    f"{updated_site['site']['name']}"
                ),
                "result": updated_site["site"],
            }
        )
    elif dattormm_plan:
        actions.append(
            {
                "system": "Datto RMM",
                "status": "noop",
                "details": "Site name already matched the target name.",
                "result": {
                    "id": str(dattormm_plan["entity_id"]),
                    "name": dattormm_plan["current_name"],
                },
            }
        )

    halopsa_plan = next((item for item in plan["systems"] if item["system"] == "HaloPSA"), None)
    if halopsa_plan and halopsa_plan["needs_change"]:
        updated_client = await update_halopsa_client(
            client_id=str(halopsa_plan["entity_id"]),
            name=desired_name,
        )
        await _refresh_mapping_name(
            organization_id=org["id"],
            system="HaloPSA",
            entity_id=str(halopsa_plan["entity_id"]),
            entity_name=updated_client["client"]["name"],
        )
        actions.append(
            {
                "system": "HaloPSA",
                "status": "renamed",
                "details": (
                    f"{halopsa_plan['current_name']} -> "
                    f"{updated_client['client']['name']}"
                ),
                "result": updated_client["client"],
            }
        )
    elif halopsa_plan:
        actions.append(
            {
                "system": "HaloPSA",
                "status": "noop",
                "details": "Client name already matched the target name.",
                "result": {
                    "id": str(halopsa_plan["entity_id"]),
                    "name": halopsa_plan["current_name"],
                },
            }
        )

    huntress_plan = next((item for item in plan["systems"] if item["system"] == "Huntress"), None)
    if huntress_plan and huntress_plan["needs_change"]:
        try:
            updated_org = await update_huntress_organization(
                organization_id=str(huntress_plan["entity_id"]),
                name=desired_name,
            )
            await _refresh_mapping_name(
                organization_id=org["id"],
                system="Huntress",
                entity_id=str(huntress_plan["entity_id"]),
                entity_name=updated_org["organization"]["name"],
            )
            actions.append(
                {
                    "system": "Huntress",
                    "status": "renamed",
                    "details": (
                        f"{huntress_plan['current_name']} -> "
                        f"{updated_org['organization']['name']}"
                    ),
                    "result": updated_org["organization"],
                }
            )
        except AttributeError as exc:
            if "OrganizationUpdateParameters" not in str(exc):
                raise
            forced_unsupported.append(
                {
                    **huntress_plan,
                    "notes": [
                        *list(huntress_plan.get("notes") or []),
                        "Huntress rename is not available in the current generated client surface.",
                    ],
                }
            )
            actions.append(
                {
                    "system": "Huntress",
                    "status": "manual",
                    "details": "Skipped because the current Huntress client does not expose the required update operation.",
                    "result": {
                        "id": str(huntress_plan["entity_id"]),
                        "name": huntress_plan["current_name"],
                    },
                }
            )
    elif huntress_plan:
        actions.append(
            {
                "system": "Huntress",
                "status": "noop",
                "details": "Organization name already matched the target name.",
                "result": {
                    "id": str(huntress_plan["entity_id"]),
                    "name": huntress_plan["current_name"],
                },
            }
        )

    dnsfilter_plan = next((item for item in plan["systems"] if item["system"] == "DNSFilter"), None)
    if dnsfilter_plan and dnsfilter_plan["needs_change"]:
        updated_org = await update_dnsfilter_organization(
            organization_id=str(dnsfilter_plan["entity_id"]),
            name=desired_name,
        )
        await _refresh_mapping_name(
            organization_id=org["id"],
            system="DNSFilter",
            entity_id=str(dnsfilter_plan["entity_id"]),
            entity_name=updated_org["organization"]["name"],
            mapping_config=dnsfilter_plan.get("mapping_config"),
        )
        dnsfilter_result = {
            "organization": updated_org["organization"],
            "networks": [],
        }
        network_actions = (
            ((dnsfilter_plan.get("mapping_config") or {}).get("network_actions")) or []
        )
        if network_actions:
            client = await get_dnsfilter_client(scope=org["id"])
            try:
                for item in network_actions:
                    if not item.get("needs_change"):
                        dnsfilter_result["networks"].append(
                            {
                                "network_id": item["network_id"],
                                "name": item["current_name"],
                                "status": "noop",
                            }
                        )
                        continue
                    updated_network = await client.update_network(
                        network_id=str(item["network_id"]),
                        name=str(item["target_name"]),
                    )
                    normalized_network = DNSFilterClient.normalize_network(updated_network)
                    dnsfilter_result["networks"].append(
                        {
                            "network_id": str(item["network_id"]),
                            "name": normalized_network["name"],
                            "status": "renamed",
                        }
                    )
            finally:
                await client.close()

        renamed_networks = [
            item for item in dnsfilter_result["networks"] if item["status"] == "renamed"
        ]
        details = f"{dnsfilter_plan['current_name']} -> {updated_org['organization']['name']}"
        if renamed_networks:
            details += (
                f"; renamed {len(renamed_networks)} network"
                f"{'s' if len(renamed_networks) != 1 else ''}"
            )
        actions.append(
            {
                "system": "DNSFilter",
                "status": "renamed",
                "details": details,
                "result": dnsfilter_result,
            }
        )
    elif dnsfilter_plan:
        actions.append(
            {
                "system": "DNSFilter",
                "status": "noop",
                "details": "Organization name already matched the target name.",
                "result": {
                    "organization": {
                        "id": str(dnsfilter_plan["entity_id"]),
                        "name": dnsfilter_plan["current_name"],
                    },
                    "networks": (
                        ((dnsfilter_plan.get("mapping_config") or {}).get("network_actions")) or []
                    ),
                },
            }
        )

    connectsecure_plan = next((item for item in plan["systems"] if item["system"] == "ConnectSecure"), None)
    if connectsecure_plan and connectsecure_plan["needs_change"]:
        updated_company = await update_connectsecure_company(
            company_id=str(connectsecure_plan["entity_id"]),
            name=desired_name,
        )
        await _refresh_mapping_name(
            organization_id=org["id"],
            system="ConnectSecure",
            entity_id=str(connectsecure_plan["entity_id"]),
            entity_name=updated_company["company"]["name"],
        )
        actions.append(
            {
                "system": "ConnectSecure",
                "status": "renamed",
                "details": (
                    f"{connectsecure_plan['current_name']} -> "
                    f"{updated_company['company']['name']}"
                ),
                "result": updated_company["company"],
            }
        )
    elif connectsecure_plan:
        actions.append(
            {
                "system": "ConnectSecure",
                "status": "noop",
                "details": "Company name already matched the target name.",
                "result": {
                    "id": str(connectsecure_plan["entity_id"]),
                    "name": connectsecure_plan["current_name"],
                },
            }
        )

    pax8_plan = next((item for item in plan["systems"] if item["system"] == "Pax8"), None)
    if pax8_plan and pax8_plan["needs_change"]:
        updated_company = await update_pax8_company(
            company_id=str(pax8_plan["entity_id"]),
            name=desired_name,
        )
        await _refresh_mapping_name(
            organization_id=org["id"],
            system="Pax8",
            entity_id=str(pax8_plan["entity_id"]),
            entity_name=updated_company["company"]["name"],
        )
        actions.append(
            {
                "system": "Pax8",
                "status": "renamed",
                "details": (
                    f"{pax8_plan['current_name']} -> "
                    f"{updated_company['company']['name']}"
                ),
                "result": updated_company["company"],
            }
        )
    elif pax8_plan:
        actions.append(
            {
                "system": "Pax8",
                "status": "noop",
                "details": "Company name already matched the target name.",
                "result": {
                    "id": str(pax8_plan["entity_id"]),
                    "name": pax8_plan["current_name"],
                },
            }
        )

    unsupported = [
        item
        for item in plan["systems"]
        if item["system"] not in {
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
        } and item["needs_change"]
    ]
    unsupported.extend(forced_unsupported)
    sync_results: list[dict[str, Any]] = []
    if refresh_mappings:
        sync_results = await _run_post_rename_syncs(actions)
    if ticket and (actions or unsupported):
        await create_autotask_ticket_note(
            ticket_id=ticket["id"],
            description=_render_execution_note(
                desired_name=desired_name,
                actions=actions,
                unsupported=unsupported,
                sync_results=sync_results,
                audit_follow_up=plan.get("audit_follow_up") or [],
            ),
        )

    return {
        "dry_run": False,
        "plan": plan,
        "ticket": ticket,
        "actions": actions,
        "sync_results": sync_results,
        "unsupported_systems": unsupported,
        "audit_follow_up": plan.get("audit_follow_up") or [],
    }
