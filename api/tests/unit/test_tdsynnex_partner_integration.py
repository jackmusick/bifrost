from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = REPO_ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bifrost import integrations
from features.tdsynnex_partner.workflows.tools import (
    get_invoice,
    get_order,
    get_quote_status,
    get_shipment_details,
)
from modules import tdsynnex_partner


@pytest.mark.asyncio
async def test_get_client_uses_default_base_url(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "TD SYNNEX Partner API"
        assert scope == "global"
        return SimpleNamespace(
            config={"client_id": "cid", "client_secret": "csecret"},
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await tdsynnex_partner.get_client(scope="global")
    try:
        assert client._base_url == tdsynnex_partner.TDSynnexPartnerClient.BASE_URL
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_credentials(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={"client_id": "cid"})

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="client_secret"):
        await tdsynnex_partner.get_client(scope="global")


def test_extract_primary_record_prefers_first_list_entry():
    payload = [
        {"orderNumber": "123", "orderStatus": "Open"},
        {"orderNumber": "456", "orderStatus": "Closed"},
    ]

    result = tdsynnex_partner.TDSynnexPartnerClient.extract_primary_record(payload)

    assert result == {"orderNumber": "123", "orderStatus": "Open"}


@pytest.mark.asyncio
async def test_get_order_tool_summarizes_response(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def get_order(self, order_no: str, *, order_type: str | None = None):
            assert order_no == "134492797"
            assert order_type == "SO"
            return [
                {
                    "orderNumber": "134492797",
                    "purchaseOrderNumber": "PO123",
                    "salesOrderNumber": "SO123",
                    "invoiceNumber": "INV123",
                    "orderStatus": "Open",
                    "orderPlacedDate": "2022-11-02T00:00:00Z",
                    "total": "500.00",
                }
            ]

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    monkeypatch.setattr(tdsynnex_partner, "get_client", fake_get_client)

    result = await get_order("134492797", order_type="SO")

    assert result["summary"] == {
        "order_number": "134492797",
        "purchase_order_number": "PO123",
        "sales_order_number": "SO123",
        "invoice_number": "INV123",
        "order_status": "Open",
        "order_placed_date": "2022-11-02T00:00:00Z",
        "total": "500.00",
    }
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_get_shipment_details_tool_summarizes_response(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def get_shipment_details(self, order_no: str):
            assert order_no == "SO-987654"
            return {
                "orderNumber": "SO-987654",
                "purchaseOrder": "PO-TEST-002",
                "orderStatus": "Open",
                "lines": [{"lineNumber": "1"}],
            }

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        return fake_client

    monkeypatch.setattr(tdsynnex_partner, "get_client", fake_get_client)

    result = await get_shipment_details("SO-987654")

    assert result["summary"] == {
        "order_number": "SO-987654",
        "purchase_order": "PO-TEST-002",
        "order_status": "Open",
        "line_count": 1,
    }
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_get_invoice_tool_summarizes_response(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def get_invoice(self, invoice_no: str, *, invoice_type: str = "IV"):
            assert invoice_no == "INV-001"
            assert invoice_type == "IV"
            return [
                {
                    "invoiceNumber": "INV-001",
                    "salesOrderNumber": "SO123",
                    "purchaseOrderNumber": "PO123",
                    "status": "Open",
                    "invoiceDate": "2026-03-27",
                    "totalInvoiceAmount": 123.45,
                    "customerName": "Acme Dental",
                }
            ]

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        return fake_client

    monkeypatch.setattr(tdsynnex_partner, "get_client", fake_get_client)

    result = await get_invoice("INV-001")

    assert result["summary"] == {
        "invoice_number": "INV-001",
        "sales_order_number": "SO123",
        "purchase_order_number": "PO123",
        "status": "Open",
        "invoice_date": "2026-03-27",
        "total_invoice_amount": 123.45,
        "customer_name": "Acme Dental",
    }
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_get_quote_status_tool_returns_primary_record(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def get_quote_status(self, order_no: str):
            assert order_no == "134492797"
            return [{"quoteId": "Q-123", "status": "Ready"}]

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        return fake_client

    monkeypatch.setattr(tdsynnex_partner, "get_client", fake_get_client)

    result = await get_quote_status("134492797")

    assert result["summary"] == {"quoteId": "Q-123", "status": "Ready"}
    assert fake_client.closed is True
