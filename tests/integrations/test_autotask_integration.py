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

from bifrost import integrations, organizations
from features.autotask.workflows.close_ticket import close_autotask_ticket
from features.autotask.workflows.create_ticket import create_autotask_ticket
from features.autotask.workflows.create_ticket_note import create_autotask_ticket_note
from features.autotask.workflows.data_providers import list_autotask_companies
from features.autotask.workflows.get_company import get_autotask_company
from features.autotask.workflows.get_ticket import get_autotask_ticket
from features.autotask.workflows.update_company import update_autotask_company
from features.autotask.workflows.sync_customers import sync_autotask_customers
from modules import autotask


def _company(company_id: int | None, name: str | None) -> dict:
    return {"id": company_id, "companyName": name}


@pytest.mark.asyncio
async def test_get_client_uses_scoped_mapping(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "Autotask"
        assert scope == "org-123"
        return SimpleNamespace(
            config={
                "base_url": "https://webservices.example.com/atservicesrest",
                "api_integration_code": "code",
                "username": "user",
                "secret": "secret",
            },
            entity_id="456",
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await autotask.get_client(scope="org-123")
    try:
        assert client.company_id == "456"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_credentials(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={"base_url": "https://webservices.example.com"})

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="api_integration_code"):
        await autotask.get_client(scope="global")


def test_normalize_company():
    normalized = autotask.AutotaskClient.normalize_company(
        {"id": 123, "companyName": "Acme Dental"}
    )

    assert normalized == {"id": "123", "name": "Acme Dental"}


def test_normalize_company_unwraps_item():
    normalized = autotask.AutotaskClient.normalize_company(
        {"item": {"id": 210, "companyName": "Auto Outfitters"}}
    )

    assert normalized == {"id": "210", "name": "Auto Outfitters"}


@pytest.mark.asyncio
async def test_client_update_company():
    client = autotask.AutotaskClient(
        base_url="https://webservices.example.com/atservicesrest",
        api_integration_code="code",
        username="user",
        secret="secret",
        company_id="456",
    )

    requests: list[tuple[str, str, dict | None]] = []

    async def fake_request(method: str, url: str, *, json_body=None):
        requests.append((method, url, json_body))
        if method == "PATCH":
            return SimpleNamespace(json=lambda: {"itemId": 456})
        return SimpleNamespace(
            json=lambda: {
                "id": 456,
                "companyName": "Updated Company",
            }
        )

    client._request = fake_request  # type: ignore[method-assign]

    try:
        company = await client.update_company(company_name="Updated Company")
    finally:
        await client.close()

    assert company["companyName"] == "Updated Company"
    assert requests == [
        (
            "PATCH",
            "https://webservices.example.com/atservicesrest/V1.0/Companies",
            {
                "id": 456,
                "companyName": "Updated Company",
            },
        ),
        (
            "GET",
            "https://webservices.example.com/atservicesrest/V1.0/Companies/456",
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_update_autotask_company_workflow(monkeypatch):
    calls: list[dict] = []

    class FakeClient:
        async def update_company(self, **kwargs):
            calls.append(kwargs)
            return {"id": 210, "companyName": "Renamed Co"}

        async def close(self):
            return None

    async def fake_get_client():
        return FakeClient()

    monkeypatch.setattr(
        "modules.autotask.get_client",
        fake_get_client,
        raising=False,
    )

    result = await update_autotask_company(company_id="210", company_name="Renamed Co")

    assert result == {
        "company": {"id": "210", "name": "Renamed Co"},
        "raw": {"id": 210, "companyName": "Renamed Co"},
    }
    assert calls == [{"company_id": "210", "company_name": "Renamed Co", "extra_fields": None}]


def test_normalize_ticket():
    normalized = autotask.AutotaskClient.normalize_ticket(
        {
            "id": 987,
            "ticketNumber": "T2026-001",
            "companyID": 123,
            "title": "Automation Work",
            "status": 5,
        }
    )

    assert normalized == {
        "id": "987",
        "ticket_number": "T2026-001",
        "company_id": "123",
        "title": "Automation Work",
        "status": "5",
    }


def test_normalize_ticket_unwraps_item():
    normalized = autotask.AutotaskClient.normalize_ticket(
        {
            "item": {
                "id": 159267,
                "ticketNumber": "AT-159267",
                "companyID": 210,
                "title": "Bifrost automation test ticket",
                "status": 1,
            }
        }
    )

    assert normalized == {
        "id": "159267",
        "ticket_number": "AT-159267",
        "company_id": "210",
        "title": "Bifrost automation test ticket",
        "status": "1",
    }


@pytest.mark.asyncio
async def test_client_create_ticket_uses_scoped_company_id():
    client = autotask.AutotaskClient(
        base_url="https://webservices.example.com/atservicesrest",
        api_integration_code="code",
        username="user",
        secret="secret",
        company_id="456",
    )

    requests: list[tuple[str, str, dict | None]] = []

    async def fake_request(method: str, url: str, *, json_body=None):
        requests.append((method, url, json_body))
        if method == "POST":
            return SimpleNamespace(json=lambda: {"itemId": 999})
        return SimpleNamespace(
            json=lambda: {
                "id": 999,
                "ticketNumber": "T2026-999",
                "companyID": 456,
                "title": "Create ticket",
                "status": 1,
            }
        )

    client._request = fake_request  # type: ignore[method-assign]

    try:
        ticket = await client.create_ticket(
            title="Create ticket",
            description="Created by automation",
            queue_id="12",
            issue_type="34",
            status="1",
            priority="2",
        )
    finally:
        await client.close()

    assert ticket["id"] == 999
    assert requests == [
        (
            "POST",
            "https://webservices.example.com/atservicesrest/V1.0/Tickets",
            {
                "companyID": 456,
                "title": "Create ticket",
                "description": "Created by automation",
                "queueID": 12,
                "issueType": 34,
                "status": 1,
                "priority": 2,
            },
        ),
        (
            "GET",
            "https://webservices.example.com/atservicesrest/V1.0/Tickets/999",
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_client_create_ticket_requires_company_id():
    client = autotask.AutotaskClient(
        base_url="https://webservices.example.com/atservicesrest",
        api_integration_code="code",
        username="user",
        secret="secret",
    )

    try:
        with pytest.raises(RuntimeError, match="company ID is required"):
            await client.create_ticket(title="Create ticket")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_client_get_ticket():
    client = autotask.AutotaskClient(
        base_url="https://webservices.example.com/atservicesrest",
        api_integration_code="code",
        username="user",
        secret="secret",
    )

    requests: list[tuple[str, str, dict | None]] = []

    async def fake_request(method: str, url: str, *, json_body=None):
        requests.append((method, url, json_body))
        return SimpleNamespace(
            json=lambda: {
                "id": 123,
                "ticketNumber": "AT-123",
                "companyID": 456,
                "title": "Existing Ticket",
                "status": 1,
            }
        )

    client._request = fake_request  # type: ignore[method-assign]

    try:
        ticket = await client.get_ticket("123")
    finally:
        await client.close()

    assert ticket["ticketNumber"] == "AT-123"
    assert requests == [
        (
            "GET",
            "https://webservices.example.com/atservicesrest/V1.0/Tickets/123",
            None,
        )
    ]


@pytest.mark.asyncio
async def test_client_update_ticket():
    client = autotask.AutotaskClient(
        base_url="https://webservices.example.com/atservicesrest",
        api_integration_code="code",
        username="user",
        secret="secret",
    )

    requests: list[tuple[str, str, dict | None]] = []

    async def fake_request(method: str, url: str, *, json_body=None):
        requests.append((method, url, json_body))
        if method == "PATCH":
            return SimpleNamespace(json=lambda: {"itemId": 123})
        return SimpleNamespace(
            json=lambda: {
                "id": 123,
                "ticketNumber": "AT-123",
                "companyID": 456,
                "title": "Existing Ticket",
                "status": 5,
            }
        )

    client._request = fake_request  # type: ignore[method-assign]

    try:
        ticket = await client.update_ticket("123", status="5", resolution="Closed by test")
    finally:
        await client.close()

    assert ticket["status"] == 5
    assert requests == [
        (
            "PATCH",
            "https://webservices.example.com/atservicesrest/V1.0/Tickets",
            {"id": 123, "status": 5, "resolution": "Closed by test"},
        ),
        (
            "GET",
            "https://webservices.example.com/atservicesrest/V1.0/Tickets/123",
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_client_create_ticket_note():
    client = autotask.AutotaskClient(
        base_url="https://webservices.example.com/atservicesrest",
        api_integration_code="code",
        username="user",
        secret="secret",
    )

    requests: list[tuple[str, str, dict | None]] = []

    async def fake_request(method: str, url: str, *, json_body=None):
        requests.append((method, url, json_body))
        return SimpleNamespace(
            json=lambda: {
                "itemId": 555,
                "ticketID": 123,
                "description": "Automation note",
            }
        )

    client._request = fake_request  # type: ignore[method-assign]

    try:
        note = await client.create_ticket_note(
            ticket_id="123",
            description="Automation note",
            note_type="3",
            publish="1",
            title="Bifrost note",
        )
    finally:
        await client.close()

    assert note["itemId"] == 555
    assert requests == [
        (
            "POST",
            "https://webservices.example.com/atservicesrest/V1.0/Tickets/123/notes",
            {
                "description": "Automation note",
                "noteType": 3,
                "publish": 1,
                "title": "Bifrost note",
            },
        )
    ]


@pytest.mark.asyncio
async def test_list_autotask_companies_returns_sorted_options(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_active_companies(self):
            return [
                _company(2, "Zulu Dental"),
                _company(1, "Alpha Dental"),
                _company(None, "Missing ID"),
                _company(3, ""),
            ]

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    monkeypatch.setattr(autotask, "get_client", fake_get_client)

    result = await list_autotask_companies()

    assert result == [
        {"value": "1", "label": "Alpha Dental"},
        {"value": "2", "label": "Zulu Dental"},
    ]
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_sync_autotask_customers_maps_unmapped_customers(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_active_companies(self):
            return [
                _company(100, "Already Mapped"),
                _company(200, "Existing Org"),
                _company(300, "New Org"),
                _company(None, "Broken Company"),
            ]

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()
    created_names: list[str] = []
    mapping_calls: list[tuple[str, str, str, str]] = []

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    async def fake_list_mappings(name: str):
        assert name == "Autotask"
        return [SimpleNamespace(entity_id="100")]

    existing_org = SimpleNamespace(id="org-existing", name="Existing Org")

    async def fake_list_orgs():
        return [existing_org]

    async def fake_create_org(name: str):
        created_names.append(name)
        return SimpleNamespace(id="org-new", name=name)

    async def fake_upsert_mapping(
        name: str,
        *,
        scope: str,
        entity_id: str,
        entity_name: str,
    ):
        mapping_calls.append((name, scope, entity_id, entity_name))

    monkeypatch.setattr(autotask, "get_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_autotask_customers()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped company with no ID: {'id': None, 'companyName': 'Broken Company'}"],
    }
    assert created_names == ["New Org"]
    assert mapping_calls == [
        ("Autotask", "org-existing", "200", "Existing Org"),
        ("Autotask", "org-new", "300", "New Org"),
    ]
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_create_autotask_ticket_uses_integration_defaults(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False
            self.calls: list[dict] = []

        async def create_ticket(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "id": 321,
                "ticketNumber": "AT-321",
                "companyID": 456,
                "title": kwargs["title"],
                "status": kwargs["status"],
            }

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get(name: str, scope: str | None = None):
        assert name == "Autotask"
        return SimpleNamespace(
            config={
                "default_ticket_queue_id": "12",
                "default_ticket_issue_type": "34",
                "default_ticket_status": "1",
                "default_ticket_priority": "2",
                "default_ticket_source": "10",
            }
        )

    async def fake_get_client(scope: str | None = None):
        assert scope is None
        return fake_client

    monkeypatch.setattr(integrations, "get", fake_get)
    monkeypatch.setattr(autotask, "get_client", fake_get_client)

    result = await create_autotask_ticket(
        title="Customer rename automation",
        description="Created by Bifrost",
    )

    assert result == {
        "ticket": {
            "id": "321",
            "ticket_number": "AT-321",
            "company_id": "456",
            "title": "Customer rename automation",
            "status": "1",
        },
        "raw": {
            "id": 321,
            "ticketNumber": "AT-321",
            "companyID": 456,
            "title": "Customer rename automation",
            "status": "1",
        },
    }
    assert fake_client.calls == [
        {
            "title": "Customer rename automation",
            "description": "Created by Bifrost",
            "company_id": None,
            "queue_id": "12",
            "issue_type": "34",
            "sub_issue_type": None,
            "status": "1",
            "priority": "2",
            "source": "10",
            "due_date": None,
            "extra_fields": None,
        }
    ]
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_create_autotask_ticket_prefers_explicit_values(monkeypatch):
    class FakeClient:
        async def create_ticket(self, **kwargs):
            return {
                "id": 654,
                "ticketNumber": "AT-654",
                "companyID": 999,
                "title": kwargs["title"],
                "status": kwargs["status"],
            }

        async def close(self) -> None:
            return None

    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(
            config={
                "default_ticket_queue_id": "12",
                "default_ticket_status": "1",
            }
        )

    async def fake_get_client(scope: str | None = None):
        return FakeClient()

    monkeypatch.setattr(integrations, "get", fake_get)
    monkeypatch.setattr(autotask, "get_client", fake_get_client)

    result = await create_autotask_ticket(
        title="Override defaults",
        company_id="999",
        queue_id="77",
        status="5",
        priority="8",
        use_integration_defaults=False,
        extra_fields={"source": 42},
    )

    assert result["ticket"] == {
        "id": "654",
        "ticket_number": "AT-654",
        "company_id": "999",
        "title": "Override defaults",
        "status": "5",
    }


@pytest.mark.asyncio
async def test_get_autotask_company(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def get_company(self, company_id=None):
            assert company_id == "210"
            return {"id": 210, "companyName": "Auto Outfitters"}

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope is None
        return fake_client

    monkeypatch.setattr(autotask, "get_client", fake_get_client)

    result = await get_autotask_company(company_id="210")

    assert result == {
        "company": {"id": "210", "name": "Auto Outfitters"},
        "raw": {"id": 210, "companyName": "Auto Outfitters"},
    }
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_get_autotask_ticket(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def get_ticket(self, ticket_id):
            assert ticket_id == "159267"
            return {
                "id": 159267,
                "ticketNumber": "AT-159267",
                "companyID": 210,
                "title": "Bifrost automation test ticket",
                "status": 1,
            }

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope is None
        return fake_client

    monkeypatch.setattr(autotask, "get_client", fake_get_client)

    result = await get_autotask_ticket(ticket_id="159267")

    assert result == {
        "ticket": {
            "id": "159267",
            "ticket_number": "AT-159267",
            "company_id": "210",
            "title": "Bifrost automation test ticket",
            "status": "1",
        },
        "raw": {
            "id": 159267,
            "ticketNumber": "AT-159267",
            "companyID": 210,
            "title": "Bifrost automation test ticket",
            "status": 1,
        },
    }
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_close_autotask_ticket(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False
            self.calls: list[dict] = []

        async def update_ticket(self, ticket_id, **kwargs):
            self.calls.append({"ticket_id": ticket_id, **kwargs})
            return {
                "id": 159267,
                "ticketNumber": "AT-159267",
                "companyID": 210,
                "title": "Bifrost automation test ticket",
                "status": 5,
            }

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={})

    async def fake_get_client(scope: str | None = None):
        assert scope is None
        return fake_client

    monkeypatch.setattr(integrations, "get", fake_get)
    monkeypatch.setattr(autotask, "get_client", fake_get_client)

    result = await close_autotask_ticket(
        ticket_id="159267",
        resolution="Closed by automation test",
    )

    assert result == {
        "ticket": {
            "id": "159267",
            "ticket_number": "AT-159267",
            "company_id": "210",
            "title": "Bifrost automation test ticket",
            "status": "5",
        },
        "raw": {
            "id": 159267,
            "ticketNumber": "AT-159267",
            "companyID": 210,
            "title": "Bifrost automation test ticket",
            "status": 5,
        },
    }
    assert fake_client.calls == [
        {
            "ticket_id": "159267",
            "status": "5",
            "resolution": "Closed by automation test",
            "extra_fields": None,
        }
    ]
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_create_autotask_ticket_note_uses_integration_defaults(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False
            self.calls: list[dict] = []

        async def create_ticket_note(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "itemId": 777,
                "ticketID": 159267,
                "description": kwargs["description"],
            }

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(
            config={
                "default_ticket_note_type": "3",
                "default_ticket_note_publish": "1",
                "default_ticket_note_title": "Bifrost Automation Note",
            }
        )

    async def fake_get_client(scope: str | None = None):
        return fake_client

    monkeypatch.setattr(integrations, "get", fake_get)
    monkeypatch.setattr(autotask, "get_client", fake_get_client)

    result = await create_autotask_ticket_note(
        ticket_id="159267",
        description="Automation note",
    )

    assert result == {
        "note": {
            "itemId": 777,
            "ticketID": 159267,
            "description": "Automation note",
        }
    }
    assert fake_client.calls == [
        {
            "ticket_id": "159267",
            "description": "Automation note",
            "note_type": "3",
            "publish": "1",
            "title": "Bifrost Automation Note",
            "extra_fields": None,
        }
    ]
    assert fake_client.closed is True
