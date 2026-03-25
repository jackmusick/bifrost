"""
HaloPSA shared data providers.

Reusable data provider workflows for HaloPSA entities, intended for use
in forms and other workflows that need dropdown/select options.
"""

import logging

from bifrost import data_provider, context, UserError
from modules import halopsa
from modules.extensions.halopsa import resolve_client_id

logger = logging.getLogger(__name__)


@data_provider(
    name="HaloPSA Clients",
    description="Returns all active HaloPSA clients as {label, value} pairs for use in forms and dropdowns.",
    cache_ttl_seconds=300,
)
async def halopsa_clients() -> list[dict]:
    """
    Fetches all clients from HaloPSA with pagination and returns them in the
    standard data provider format: [{"label": "Client Name", "value": client_id}, ...]

    Value is the client ID as an integer matching HaloPSA's native ID type.
    HaloPSA max page size is 100. Pagination uses pageinate=True, page_size, page_no.
    """
    all_clients = []
    page_no = 1
    page_size = 100

    while True:
        result = await halopsa.list_clients(pageinate=True, page_size=page_size, page_no=page_no)

        clients = getattr(result, "clients", None) or []
        record_count = getattr(result, "record_count", None)

        for client in clients:
            client_id = getattr(client, "id", None)
            name = getattr(client, "name", None)
            if client_id is None or not name:
                continue
            all_clients.append({"label": name, "value": client_id})

        # Stop if we've fetched everything
        if not clients:
            break
        if record_count is not None and page_no * page_size >= record_count:
            break
        if len(clients) < page_size:
            break

        page_no += 1

    return sorted(all_clients, key=lambda r: r["label"].lower())


@data_provider(
    name="HaloPSA Client Sites",
    description="Sites for the org's HaloPSA client, excluding inventory/stock locations",
    cache_ttl_seconds=300,
)
async def halo_client_sites(org_id: str = "") -> list[dict]:
    """Returns active, non-inventory sites for the org's linked HaloPSA client."""
    if org_id:
        context.set_scope(org_id)
    elif not context.org_id:
        return []

    try:
        client_id = await resolve_client_id(org_id or context.org_id)
    except Exception as e:
        logger.warning(f"Could not resolve HaloPSA client for org {effective_org}: {e}")
        return []

    try:
        result = await halopsa.list_sites(client_id=client_id, includeinactive=False)
    except Exception as e:
        logger.error(f"Failed to list HaloPSA sites for client {client_id}: {e}")
        raise UserError("Unable to load sites. Is the HaloPSA integration connected?")

    raw_sites = getattr(result, "sites", None) or (
        result.get("sites", []) if isinstance(result, dict) else []
    )

    results = []
    for site in raw_sites:
        site_id = getattr(site, "id", None) or (site.get("id") if isinstance(site, dict) else None)
        site_name = getattr(site, "name", None) or (site.get("name") if isinstance(site, dict) else None)
        if not site_id or not site_name:
            continue
        if getattr(site, "isstocklocation", False):
            continue

        results.append({"label": site_name, "value": str(site_id)})

    return sorted(results, key=lambda r: r["label"])


@data_provider(
    name="HaloPSA Open Tickets",
    description="Open HaloPSA tickets for a given org, for use in ticket selector dropdowns.",
    cache_ttl_seconds=120,
)
async def halo_open_tickets(org_id: str = "") -> list[dict]:
    """Returns open tickets for the org as {label, value} pairs."""
    if org_id:
        context.set_scope(org_id)
    elif not context.org_id:
        return []

    try:
        client_id = await resolve_client_id(org_id)
        result = await halopsa.list_tickets(
            client_id=client_id,
            open_only=True,
            pageinate=True,
            page_size=50,
            page_no=1,
            order="dateoccurred",
            orderdesc=True,
        )
        tickets_raw = (
            result.get("tickets", []) if isinstance(result, dict)
            else getattr(result, "tickets", []) or []
        )
        return [
            {
                "label": f"#{t.get('id')} \u2013 {t.get('summary', '')}",
                "value": str(t.get("id")),
            }
            for t in tickets_raw
            if t.get("id") and t.get("summary")
        ]
    except Exception as e:
        logger.error(f"Failed to fetch open tickets for org {org_id}: {e}")
        return []
