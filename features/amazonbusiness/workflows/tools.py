"""
Amazon Business lookup tools.

These tools are global, lookup-oriented helpers for procurement teams. They work
from known order and package identifiers and intentionally avoid broader
customer/onboarding assumptions in the first pass.
"""

from __future__ import annotations

from bifrost import tool


@tool(
    name="Amazon Business: Get Order Details",
    description="Look up Amazon Business order details by external order ID.",
    category="Amazon Business",
    tags=["amazon", "amazon-business", "orders", "procurement"],
)
async def get_order_details(external_id: str) -> dict:
    """Return Amazon Business order details and a normalized summary."""
    from modules.amazonbusiness import AmazonBusinessClient, get_client

    client = await get_client(scope="global")
    try:
        order = await client.get_order_details(external_id)
    finally:
        await client.close()

    return {
        "external_id": external_id,
        "summary": AmazonBusinessClient.summarize_order_details(order),
        "order": order,
    }


@tool(
    name="Amazon Business: Get Package Tracking Details",
    description="Look up Amazon Business package tracking details for an order shipment package.",
    category="Amazon Business",
    tags=["amazon", "amazon-business", "tracking", "shipments", "procurement"],
)
async def get_package_tracking_details(
    order_id: str,
    shipment_id: str,
    package_id: str,
    region: str | None = None,
    locale: str | None = None,
) -> dict:
    """Return package tracking details and a normalized summary."""
    from modules.amazonbusiness import AmazonBusinessClient, get_client

    client = await get_client(scope="global")
    try:
        package = await client.get_package_tracking_details(
            order_id=order_id,
            shipment_id=shipment_id,
            package_id=package_id,
            region=region,
            locale=locale,
        )
    finally:
        await client.close()

    return {
        "order_id": order_id,
        "shipment_id": shipment_id,
        "package_id": package_id,
        "summary": AmazonBusinessClient.summarize_package_tracking(package),
        "package": package,
    }
