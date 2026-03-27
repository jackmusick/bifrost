from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bifrost import integrations
from features.amazonbusiness.workflows.tools import (
    get_order_details,
    get_package_tracking_details,
)
from modules import amazonbusiness


@pytest.mark.asyncio
async def test_get_client_uses_default_region_base_url(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "Amazon Business"
        assert scope == "global"
        return SimpleNamespace(
            config={
                "client_id": "client-id",
                "client_secret": "client-secret",
                "refresh_token": "refresh-token",
                "buyer_email": "buyer@example.com",
            }
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await amazonbusiness.get_client()
    try:
        assert client._base_url == amazonbusiness.AmazonBusinessClient.REGION_BASE_URLS["NA"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_credentials(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={"client_id": "client-id"})

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="client_secret"):
        await amazonbusiness.get_client()


def test_client_rejects_invalid_region():
    with pytest.raises(ValueError, match="Unsupported Amazon Business api_region"):
        amazonbusiness.AmazonBusinessClient(
            client_id="client-id",
            client_secret="client-secret",
            refresh_token="refresh-token",
            buyer_email="buyer@example.com",
            api_region="APAC",
        )


def test_summarize_order_details_collects_tracking_numbers():
    payload = {
        "lineItems": [
            {
                "acceptedItems": [
                    {
                        "artifacts": [
                            {
                                "acceptanceArtifactType": "OrderIdentifier",
                                "identifier": "113-2725493-0200000",
                            },
                            {
                                "acceptanceArtifactType": "ShipmentGroup",
                                "packageReferences": [
                                    {
                                        "packageReferenceType": "CarrierTrackingNumber",
                                        "value": "TBA3074541AJSBS",
                                    }
                                ],
                            },
                        ]
                    }
                ],
                "rejectedItems": [],
            }
        ],
        "acceptanceArtifacts": [],
        "rejectionArtifacts": [],
    }

    assert amazonbusiness.AmazonBusinessClient.summarize_order_details(payload) == {
        "line_item_count": 1,
        "accepted_item_count": 1,
        "rejected_item_count": 0,
        "acceptance_artifact_count": 0,
        "rejection_artifact_count": 0,
        "order_identifiers": ["113-2725493-0200000"],
        "tracking_numbers": ["TBA3074541AJSBS"],
    }


def test_summarize_package_tracking():
    payload = {
        "packageStatus": "OUT_FOR_DELIVERY",
        "trackingNumber": "TBA3074541AJSBS",
        "carrierName": "Amazon",
        "deliveryDate": "2026-03-28T03:00:00Z",
        "trackingEvents": [
            {
                "eventCode": "OUT_FOR_DELIVERY",
                "eventDate": "2026-03-27T12:00:00Z",
            }
        ],
    }

    assert amazonbusiness.AmazonBusinessClient.summarize_package_tracking(payload) == {
        "package_status": "OUT_FOR_DELIVERY",
        "tracking_number": "TBA3074541AJSBS",
        "carrier_name": "Amazon",
        "delivery_date": "2026-03-28T03:00:00Z",
        "tracking_event_count": 1,
        "latest_event": {
            "eventCode": "OUT_FOR_DELIVERY",
            "eventDate": "2026-03-27T12:00:00Z",
        },
    }


@pytest.mark.asyncio
async def test_tools_return_summary(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def get_order_details(self, external_id: str, *, buyer_email=None):
            assert external_id == "external-123"
            return {
                "lineItems": [
                    {
                        "acceptedItems": [
                            {
                                "artifacts": [
                                    {
                                        "acceptanceArtifactType": "OrderIdentifier",
                                        "identifier": "113-2725493-0200000",
                                    }
                                ]
                            }
                        ],
                        "rejectedItems": [],
                    }
                ]
            }

        async def get_package_tracking_details(
            self,
            *,
            order_id: str,
            shipment_id: str,
            package_id: str,
            region=None,
            locale=None,
            buyer_email=None,
        ):
            assert order_id == "113-2725493-0200000"
            assert shipment_id == "2194640307TSGAH"
            assert package_id == "TBA3074541AJSBS"
            assert region == "US"
            assert locale == "en_US"
            return {
                "packageStatus": "DELIVERED",
                "trackingNumber": "TBA3074541AJSBS",
                "carrierName": "Amazon",
                "deliveryDate": "2026-03-28T03:00:00Z",
                "trackingEvents": [],
            }

        async def close(self) -> None:
            self.closed = True

    async def fake_get_client(scope: str | None = "global"):
        assert scope == "global"
        return FakeClient()

    monkeypatch.setattr(amazonbusiness, "get_client", fake_get_client)

    order = await get_order_details("external-123")
    tracking = await get_package_tracking_details(
        order_id="113-2725493-0200000",
        shipment_id="2194640307TSGAH",
        package_id="TBA3074541AJSBS",
        region="US",
        locale="en_US",
    )

    assert order["summary"]["order_identifiers"] == ["113-2725493-0200000"]
    assert tracking["summary"]["package_status"] == "DELIVERED"
