"""
Meraki admin baseline workflows.

These workflows compare all Meraki organizations to a known-good baseline org
and optionally add/update standard Midtown admins to match that baseline.
"""

from __future__ import annotations

import asyncio

from bifrost import workflow
from modules.meraki import MerakiClient


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


async def _load_org_admin_inventory(
    *,
    baseline_org_name: str,
    include_account_statuses_csv: str,
) -> tuple[MerakiClient, dict[str, dict], dict]:
    from modules.meraki import get_client

    client = await get_client(scope="global")
    organizations = await client.list_organizations()
    include_statuses = set(_parse_csv(include_account_statuses_csv))

    semaphore = asyncio.Semaphore(8)

    async def fetch_org_admins(organization: dict) -> dict:
        normalized_org = MerakiClient.normalize_organization(organization)
        org_id = normalized_org["id"]
        org_name = normalized_org["name"] or org_id

        try:
            async with semaphore:
                admins = await client.list_organization_admins(org_id)
        except Exception as exc:
            return {
                "organization_id": org_id,
                "organization_name": org_name,
                "error": str(exc),
            }

        normalized_admins = [
            MerakiClient.normalize_admin(admin)
            for admin in admins
            if isinstance(admin, dict)
        ]

        eligible_admins = [
            admin
            for admin in normalized_admins
            if admin["email"]
            and (
                not include_statuses
                or admin["accountStatus"].lower() in include_statuses
            )
        ]

        return {
            "organization_id": org_id,
            "organization_name": org_name,
            "admins": eligible_admins,
        }

    results = await asyncio.gather(
        *(fetch_org_admins(organization) for organization in organizations)
    )

    inventory = {
        result["organization_name"]: result
        for result in results
        if result.get("organization_name")
    }

    baseline = inventory.get(baseline_org_name)
    if not baseline:
        raise RuntimeError(
            f"Baseline organization '{baseline_org_name}' was not found in Meraki."
        )
    if baseline.get("error"):
        raise RuntimeError(
            f"Baseline organization '{baseline_org_name}' could not be audited: {baseline['error']}"
        )

    return client, inventory, baseline


@workflow(
    name="Meraki: Audit Admins Against Baseline Organization",
    description="Compare Meraki org admins to a baseline organization.",
    category="Meraki",
    tags=["meraki", "audit", "admins", "baseline"],
)
async def audit_meraki_admins_against_baseline(
    baseline_org_name: str = "Midtown Technology Group",
    required_admin_emails_csv: str | None = None,
    extra_valid_admin_emails_csv: str = "eric@carbonpeaktech.com",
    excluded_org_names_csv: str = "",
    include_account_statuses_csv: str = "ok,pending,unverified",
) -> dict:
    client, inventory, baseline = await _load_org_admin_inventory(
        baseline_org_name=baseline_org_name,
        include_account_statuses_csv=include_account_statuses_csv,
    )
    try:
        baseline_templates = {
            admin["email"]: admin
            for admin in baseline["admins"]
        }
        selected_admins = set(_parse_csv(required_admin_emails_csv)) or set(
            baseline_templates
        )
        selected_admins.update(_parse_csv(extra_valid_admin_emails_csv))
        expected_admins = sorted(selected_admins)
        excluded_org_names = set(_parse_csv(excluded_org_names_csv))

        disparities = []
        errors = []
        skipped_excluded = []

        for organization_name in sorted(inventory, key=str.lower):
            result = inventory[organization_name]
            normalized_org_name = result["organization_name"].strip().lower()
            if normalized_org_name in excluded_org_names:
                skipped_excluded.append(
                    {
                        "organization_id": result["organization_id"],
                        "organization_name": result["organization_name"],
                    }
                )
                continue
            if result.get("error"):
                errors.append(
                    {
                        "organization_id": result["organization_id"],
                        "organization_name": result["organization_name"],
                        "error": result["error"],
                    }
                )
                continue

            admin_emails = sorted({admin["email"] for admin in result["admins"]})
            current_admins = set(admin_emails)
            missing_admins = sorted(
                email for email in expected_admins if email not in current_admins
            )
            extra_admins = sorted(
                email for email in current_admins if email not in expected_admins
            )

            if missing_admins or extra_admins:
                disparities.append(
                    {
                        "organization_id": result["organization_id"],
                        "organization_name": result["organization_name"],
                        "missing_admins": missing_admins,
                        "extra_admins": extra_admins,
                        "admin_count": len(current_admins),
                    }
                )

        disparities.sort(
            key=lambda item: (
                -len(item["missing_admins"]),
                item["organization_name"].lower(),
            )
        )

        return {
            "baseline_organization": baseline_org_name,
            "baseline_admins": expected_admins,
            "excluded_org_names": sorted(excluded_org_names),
            "skipped_excluded": skipped_excluded,
            "organizations_audited": len(
                [
                    item for item in inventory.values()
                    if not item.get("error")
                    and item["organization_name"].strip().lower() not in excluded_org_names
                ]
            ),
            "organizations_with_disparities": len(disparities),
            "disparities": disparities,
            "organizations_with_errors": errors,
        }
    finally:
        await client.close()


@workflow(
    name="Meraki: Sync Admins From Baseline Organization",
    description="Add or update standard Meraki admins from a baseline organization.",
    category="Meraki",
    tags=["meraki", "sync", "admins", "baseline"],
)
async def sync_meraki_admins_from_baseline(
    baseline_org_name: str = "Midtown Technology Group",
    required_admin_emails_csv: str = "",
    target_org_names_csv: str | None = None,
    excluded_org_names_csv: str = "",
    include_account_statuses_csv: str = "ok,pending,unverified",
    dry_run: bool = True,
) -> dict:
    client, inventory, baseline = await _load_org_admin_inventory(
        baseline_org_name=baseline_org_name,
        include_account_statuses_csv=include_account_statuses_csv,
    )
    try:
        baseline_templates = {
            admin["email"]: admin
            for admin in baseline["admins"]
        }

        target_admin_emails = _parse_csv(required_admin_emails_csv)
        if not target_admin_emails:
            raise RuntimeError("required_admin_emails_csv must include at least one email.")

        missing_from_baseline = sorted(
            email for email in target_admin_emails if email not in baseline_templates
        )
        if missing_from_baseline:
            raise RuntimeError(
                "These emails are not present in the baseline org: "
                + ", ".join(missing_from_baseline)
            )

        target_org_names = set(_parse_csv(target_org_names_csv))
        excluded_org_names = set(_parse_csv(excluded_org_names_csv))
        created = []
        updated = []
        unchanged = []
        skipped_errors = []
        skipped_excluded = []

        for organization_name in sorted(inventory, key=str.lower):
            result = inventory[organization_name]
            normalized_org_name = result["organization_name"].strip().lower()

            if target_org_names and normalized_org_name not in target_org_names:
                continue
            if normalized_org_name in excluded_org_names:
                skipped_excluded.append(
                    {
                        "organization_id": result["organization_id"],
                        "organization_name": result["organization_name"],
                    }
                )
                continue
            if normalized_org_name == baseline_org_name.strip().lower():
                continue

            if result.get("error"):
                skipped_errors.append(
                    {
                        "organization_id": result["organization_id"],
                        "organization_name": result["organization_name"],
                        "error": result["error"],
                    }
                )
                continue

            existing_by_email = {
                admin["email"]: admin
                for admin in result["admins"]
            }

            for email in target_admin_emails:
                template = baseline_templates[email]
                existing = existing_by_email.get(email)
                desired_tags = template["tags"]
                desired_networks = template["networks"]
                desired_name = template["name"]
                desired_access = template["orgAccess"]

                if existing is None:
                    action = {
                        "organization_id": result["organization_id"],
                        "organization_name": result["organization_name"],
                        "email": email,
                        "action": "create",
                    }
                    created.append(action)
                    if not dry_run:
                        await client.create_organization_admin(
                            result["organization_id"],
                            email=email,
                            name=desired_name,
                            org_access=desired_access,
                            tags=desired_tags,
                            networks=desired_networks,
                        )
                    continue

                drift = {}
                if existing["name"] != desired_name:
                    drift["name"] = {
                        "current": existing["name"],
                        "desired": desired_name,
                    }
                if existing["orgAccess"] != desired_access:
                    drift["orgAccess"] = {
                        "current": existing["orgAccess"],
                        "desired": desired_access,
                    }
                if sorted(existing["tags"]) != sorted(desired_tags):
                    drift["tags"] = {
                        "current": existing["tags"],
                        "desired": desired_tags,
                    }
                if sorted(existing["networks"]) != sorted(desired_networks):
                    drift["networks"] = {
                        "current": existing["networks"],
                        "desired": desired_networks,
                    }

                if drift:
                    action = {
                        "organization_id": result["organization_id"],
                        "organization_name": result["organization_name"],
                        "email": email,
                        "action": "update",
                        "drift": drift,
                    }
                    updated.append(action)
                    if not dry_run:
                        await client.update_organization_admin(
                            result["organization_id"],
                            admin_id=existing["id"],
                            name=desired_name,
                            org_access=desired_access,
                            tags=desired_tags,
                            networks=desired_networks,
                        )
                else:
                    unchanged.append(
                        {
                            "organization_id": result["organization_id"],
                            "organization_name": result["organization_name"],
                            "email": email,
                        }
                    )

        return {
            "baseline_organization": baseline_org_name,
            "target_admin_emails": target_admin_emails,
            "excluded_org_names": sorted(excluded_org_names),
            "dry_run": dry_run,
            "created": created,
            "updated": updated,
            "unchanged_count": len(unchanged),
            "skipped_excluded": skipped_excluded,
            "skipped_errors": skipped_errors,
        }
    finally:
        await client.close()


@workflow(
    name="Meraki: Remove Admin Across Organizations",
    description="Remove a specific Meraki admin email across organizations.",
    category="Meraki",
    tags=["meraki", "cleanup", "admins", "remove"],
)
async def remove_meraki_admin_across_organizations(
    admin_email: str,
    target_org_names_csv: str | None = None,
    excluded_org_names_csv: str = "",
    include_account_statuses_csv: str = "ok,pending,unverified",
    dry_run: bool = True,
) -> dict:
    normalized_email = admin_email.strip().lower()
    if not normalized_email:
        raise RuntimeError("admin_email is required.")

    client, inventory, _baseline = await _load_org_admin_inventory(
        baseline_org_name="Midtown Technology Group",
        include_account_statuses_csv=include_account_statuses_csv,
    )
    try:
        target_org_names = set(_parse_csv(target_org_names_csv))
        excluded_org_names = set(_parse_csv(excluded_org_names_csv))
        removed = []
        skipped_missing = []
        skipped_errors = []
        skipped_excluded = []

        for organization_name in sorted(inventory, key=str.lower):
            result = inventory[organization_name]
            normalized_org_name = result["organization_name"].strip().lower()

            if target_org_names and normalized_org_name not in target_org_names:
                continue
            if normalized_org_name in excluded_org_names:
                skipped_excluded.append(
                    {
                        "organization_id": result["organization_id"],
                        "organization_name": result["organization_name"],
                    }
                )
                continue
            if result.get("error"):
                skipped_errors.append(
                    {
                        "organization_id": result["organization_id"],
                        "organization_name": result["organization_name"],
                        "error": result["error"],
                    }
                )
                continue

            existing = next(
                (
                    admin
                    for admin in result["admins"]
                    if admin["email"] == normalized_email
                ),
                None,
            )
            if existing is None:
                skipped_missing.append(
                    {
                        "organization_id": result["organization_id"],
                        "organization_name": result["organization_name"],
                    }
                )
                continue

            action = {
                "organization_id": result["organization_id"],
                "organization_name": result["organization_name"],
                "email": normalized_email,
                "admin_id": existing["id"],
            }
            removed.append(action)
            if not dry_run:
                await client.delete_organization_admin(
                    result["organization_id"],
                    admin_id=existing["id"],
                )

        return {
            "admin_email": normalized_email,
            "excluded_org_names": sorted(excluded_org_names),
            "dry_run": dry_run,
            "removed": removed,
            "skipped_missing_count": len(skipped_missing),
            "skipped_excluded": skipped_excluded,
            "skipped_errors": skipped_errors,
        }
    finally:
        await client.close()
