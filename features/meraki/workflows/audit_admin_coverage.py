"""
Meraki admin coverage audit workflow.

Audits every Meraki organization visible to the configured API key, infers the
expected internal admin set from the provided email domain (or uses an explicit
email list), and reports the organizations missing one or more expected admins.
"""

from __future__ import annotations

import asyncio
import math

from bifrost import workflow
from modules.meraki import MerakiClient


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _matches_domain(email: str, domain: str) -> bool:
    normalized_domain = domain.strip().lower().lstrip("@")
    return bool(normalized_domain) and email.endswith(f"@{normalized_domain}")


@workflow(
    name="Meraki: Audit Admin Coverage",
    description="Audit Meraki organizations for missing internal admins.",
    category="Meraki",
    tags=["meraki", "audit", "admins"],
)
async def audit_meraki_admin_coverage(
    internal_email_domain: str = "midtowntg.com",
    required_admin_emails_csv: str | None = None,
    min_presence_ratio: float = 0.8,
    include_account_statuses_csv: str = "ok,pending,unverified",
) -> dict:
    """
    Audit Meraki orgs for missing internal admins.

    Args:
        internal_email_domain: Internal domain used to identify Midtown admins.
        required_admin_emails_csv: Optional explicit comma-separated expected
            email list. When omitted, the workflow infers the expected set from
            the orgs themselves.
        min_presence_ratio: For inferred mode, internal admins present in at
            least this share of orgs-with-internal-admins become "expected".
        include_account_statuses_csv: Comma-separated account statuses to count
            as active enough for this audit.
    """
    from modules.meraki import get_client

    client = await get_client(scope="global")
    try:
        organizations = await client.list_organizations()

        include_statuses = set(_parse_csv(include_account_statuses_csv))
        explicit_expected = set(_parse_csv(required_admin_emails_csv))

        semaphore = asyncio.Semaphore(8)

        async def fetch_org_admins(organization: dict) -> dict:
            normalized_org = MerakiClient.normalize_organization(organization)
            org_id = normalized_org["id"]
            org_name = normalized_org["name"] or org_id

            async with semaphore:
                admins = await client.list_organization_admins(org_id)

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

            internal_admins = sorted(
                {
                    admin["email"]
                    for admin in eligible_admins
                    if _matches_domain(admin["email"], internal_email_domain)
                }
            )

            return {
                "organization_id": org_id,
                "organization_name": org_name,
                "total_admin_count": len(normalized_admins),
                "eligible_admin_count": len(eligible_admins),
                "internal_admins": internal_admins,
                "all_admin_emails": sorted(
                    {admin["email"] for admin in eligible_admins if admin["email"]}
                ),
            }

        org_results = await asyncio.gather(
            *(fetch_org_admins(organization) for organization in organizations)
        )
    finally:
        await client.close()

    org_results = sorted(
        org_results,
        key=lambda item: item["organization_name"].lower(),
    )

    orgs_with_internal = [
        result for result in org_results if result["internal_admins"]
    ]
    internal_presence: dict[str, int] = {}
    for result in orgs_with_internal:
        for email in result["internal_admins"]:
            internal_presence[email] = internal_presence.get(email, 0) + 1

    if explicit_expected:
        expected_admins = sorted(explicit_expected)
        expected_source = "explicit"
        threshold_count = None
    else:
        denominator = max(len(orgs_with_internal), 1)
        ratio = min(max(min_presence_ratio, 0.0), 1.0)
        threshold_count = max(1, math.ceil(denominator * ratio))
        expected_admins = sorted(
            email
            for email, count in internal_presence.items()
            if count >= threshold_count
        )
        expected_source = "inferred"

    missing_orgs = []
    no_internal_admin_orgs = []
    for result in org_results:
        current_internal = set(result["internal_admins"])
        missing = sorted(email for email in expected_admins if email not in current_internal)
        if not current_internal:
            no_internal_admin_orgs.append(
                {
                    "organization_id": result["organization_id"],
                    "organization_name": result["organization_name"],
                    "total_admin_count": result["total_admin_count"],
                    "all_admin_emails": result["all_admin_emails"],
                }
            )
        if missing:
            missing_orgs.append(
                {
                    "organization_id": result["organization_id"],
                    "organization_name": result["organization_name"],
                    "missing_admins": missing,
                    "current_internal_admins": result["internal_admins"],
                    "total_admin_count": result["total_admin_count"],
                    "all_admin_emails": result["all_admin_emails"],
                }
            )

    missing_orgs.sort(
        key=lambda item: (-len(item["missing_admins"]), item["organization_name"].lower())
    )

    return {
        "internal_email_domain": internal_email_domain.strip().lower().lstrip("@"),
        "expected_admins_source": expected_source,
        "expected_admins": expected_admins,
        "presence_threshold_count": threshold_count,
        "presence_by_email": [
            {
                "email": email,
                "organization_count": count,
            }
            for email, count in sorted(
                internal_presence.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ],
        "organizations_total": len(org_results),
        "organizations_with_internal_admins": len(orgs_with_internal),
        "organizations_missing_expected_admins": missing_orgs,
        "organizations_with_no_internal_admins": no_internal_admin_orgs,
    }
