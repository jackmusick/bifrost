"""
TD SYNNEX Partner API lookup tools.

These tools are global, lookup-oriented helpers for reseller procurement data.
They work from known order or invoice identifiers and are intentionally
separate from any future StreamOne ION customer/order sync integration.
"""

from __future__ import annotations

from bifrost import tool


@tool(
    name="TD SYNNEX Partner API: Get Order",
    description="Look up TD SYNNEX reseller order details by order number, with optional order type.",
    category="TD SYNNEX Partner API",
    tags=["tdsynnex", "orders", "procurement"],
)
async def get_order(order_no: str, order_type: str | None = None) -> dict:
    """Return order detail lookup results and a normalized summary."""
    from modules.tdsynnex_partner import TDSynnexPartnerClient, get_client

    client = await get_client(scope="global")
    try:
        records = await client.get_order(order_no, order_type=order_type)
    finally:
        await client.close()

    primary = TDSynnexPartnerClient.extract_primary_record(records)
    return {
        "order_no": order_no,
        "order_type": order_type,
        "count": len(records),
        "summary": {
            "order_number": primary.get("orderNumber"),
            "purchase_order_number": primary.get("purchaseOrderNumber"),
            "sales_order_number": primary.get("salesOrderNumber"),
            "invoice_number": primary.get("invoiceNumber"),
            "order_status": primary.get("orderStatus"),
            "order_placed_date": primary.get("orderPlacedDate"),
            "total": primary.get("total"),
        },
        "records": records,
    }


@tool(
    name="TD SYNNEX Partner API: Get Shipment Details",
    description="Look up TD SYNNEX shipment details for a reseller order number.",
    category="TD SYNNEX Partner API",
    tags=["tdsynnex", "shipments", "procurement"],
)
async def get_shipment_details(order_no: str) -> dict:
    """Return shipment details and a normalized summary for an order."""
    from modules import tdsynnex_partner

    client = await tdsynnex_partner.get_client(scope="global")
    try:
        shipment = await client.get_shipment_details(order_no)
    finally:
        await client.close()

    lines = shipment.get("lines", []) if isinstance(shipment, dict) else []
    return {
        "order_no": order_no,
        "summary": {
            "order_number": shipment.get("orderNumber"),
            "purchase_order": shipment.get("purchaseOrder"),
            "order_status": shipment.get("orderStatus"),
            "line_count": len(lines) if isinstance(lines, list) else 0,
        },
        "shipment": shipment,
    }


@tool(
    name="TD SYNNEX Partner API: Get Invoice",
    description="Look up TD SYNNEX invoice details by invoice number and type.",
    category="TD SYNNEX Partner API",
    tags=["tdsynnex", "invoices", "procurement"],
)
async def get_invoice(invoice_no: str, invoice_type: str = "IV") -> dict:
    """Return invoice lookup results and a normalized summary."""
    from modules.tdsynnex_partner import TDSynnexPartnerClient, get_client

    client = await get_client(scope="global")
    try:
        records = await client.get_invoice(invoice_no, invoice_type=invoice_type)
    finally:
        await client.close()

    primary = TDSynnexPartnerClient.extract_primary_record(records)
    return {
        "invoice_no": invoice_no,
        "invoice_type": invoice_type,
        "count": len(records),
        "summary": {
            "invoice_number": primary.get("invoiceNumber"),
            "sales_order_number": primary.get("salesOrderNumber"),
            "purchase_order_number": primary.get("purchaseOrderNumber"),
            "status": primary.get("status"),
            "invoice_date": primary.get("invoiceDate"),
            "total_invoice_amount": primary.get("totalInvoiceAmount"),
            "customer_name": primary.get("customerName"),
        },
        "records": records,
    }


@tool(
    name="TD SYNNEX Partner API: Get Quote Status",
    description="Look up TD SYNNEX quote status by reseller order number.",
    category="TD SYNNEX Partner API",
    tags=["tdsynnex", "quotes", "procurement"],
)
async def get_quote_status(order_no: str) -> dict:
    """Return quote status lookup results and a normalized summary."""
    from modules.tdsynnex_partner import TDSynnexPartnerClient, get_client

    client = await get_client(scope="global")
    try:
        records = await client.get_quote_status(order_no)
    finally:
        await client.close()

    primary = TDSynnexPartnerClient.extract_primary_record(records)
    return {
        "order_no": order_no,
        "count": len(records),
        "summary": primary,
        "records": records,
    }
