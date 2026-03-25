"""
Microsoft Exchange Online Data Providers

Data providers that use Exchange Online PowerShell cmdlets.
"""

import logging

from bifrost import data_provider, context, UserError

logger = logging.getLogger(__name__)


@data_provider(
    name="Exchange Shared Mailboxes",
    description="Shared mailboxes from Exchange Online via Get-Mailbox",
    cache_ttl_seconds=300,
)
async def list_shared_mailboxes(org_id: str = "", domain: str = "") -> list[dict]:
    """Returns shared mailboxes via Exchange Online Get-Mailbox.

    Uses recipientTypeDetails filter to return only actual shared mailboxes,
    excluding disabled user accounts and other mailbox types.
    """
    from modules.microsoft.exchange import create_exchange_client

    if org_id:
        context.set_scope(org_id)
    effective_org = org_id or context.org_id

    try:
        exchange = await create_exchange_client(org_id=effective_org)
        results = exchange.get_mailboxes(
            result_size="Unlimited",
            filter_expr='{recipienttypedetails -eq "SharedMailbox"}',
        )

        if not results:
            return []

        # Normalize: get_mailboxes returns a single dict if only one result
        if isinstance(results, dict):
            results = [results]

        domain_suffix = f"@{domain.lower()}" if domain else ""
        mailboxes = []
        for mb in results:
            email = (mb.get("PrimarySmtpAddress") or mb.get("WindowsEmailAddress") or "").strip()
            if not email:
                continue
            if domain_suffix and not email.lower().endswith(domain_suffix):
                continue
            display_name = mb.get("DisplayName") or email
            mailboxes.append({
                "label": f"{display_name} ({email})",
                "value": email,
            })

        return sorted(mailboxes, key=lambda r: r["label"])

    except UserError:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch shared mailboxes: {e}")
        raise UserError("Unable to load shared mailboxes. Is the Microsoft integration connected?")
