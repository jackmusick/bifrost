"""
Cove Data Protection (N-able Backup) API Client

Authentication: API credentials (username/password for API access)
Protocol: JSON-RPC (not REST!)
Base URL: https://api.backup.management/jsonapi
Docs: https://documentation.n-able.com/covedataprotection/USERGUIDE/documentation/Content/service-management/json-api/home.htm

Required config on the "Cove Data Protection" integration:
- cove_username: API username (email address)
- cove_password: API password

Note: This is a JSON-RPC API, not REST. All requests POST to /jsonapi.
The visa token is a top-level field on every request/response body (not inside params).
Many responses have a double-nested result: body.result.result - this module unwraps that.
"""

from __future__ import annotations

import httpx
from typing import Any
import uuid


# ---------------------------------------------------------------------------
# Column code mapping for EnumerateAccountStatistics
# Full reference: https://documentation.n-able.com/covedataprotection/USERGUIDE/documentation/Content/service-management/json-api/API-column-codes.htm
# ---------------------------------------------------------------------------

COLUMN_CODES: dict[str, str] = {
    # Primary device properties
    "I0": "device_id",
    "I1": "device_name",
    "I2": "device_name_alias",
    "I3": "password",
    "I4": "creation_date",
    "I5": "expiration_date",
    "I8": "customer",
    "I9": "product_id",
    "I10": "product",
    "I15": "email",
    "I39": "retention_units",
    "I54": "profile_id",
    # Installation details
    "I16": "os_version",
    "I17": "client_version",
    "I18": "computer_name",
    "I19": "internal_ips",
    "I21": "mac_address",
    "I24": "time_offset",
    "I32": "os_type",
    "I44": "computer_manufacturer",
    "I45": "computer_model",
    "I46": "installation_id",
    "I47": "installation_mode",
    "I74": "unattended_account_id",
    "I75": "first_installation_flag",
    # Storage info
    "I11": "storage_location",
    "I14": "used_storage_bytes",
    "I26": "cabinet_storage_efficiency",
    "I27": "total_cabinets_count",
    "I28": "efficient_cabinets_0_25",
    "I29": "efficient_cabinets_26_50",
    "I30": "efficient_cabinets_50_75",
    "I31": "used_virtual_storage_bytes",
    "I36": "storage_status",
    # Feature usage
    "I78": "active_data_sources",
    "I33": "seeding_mode",
    "I35": "lsv_enabled",
    "I37": "lsv_status",
    # Data source statistics (F codes)
    "F00": "last_session_status",
    "F01": "last_session_selected_count",
    "F02": "last_session_processed_count",
    "F03": "last_session_selected_size_bytes",
    "F04": "last_session_processed_size_bytes",
    "F05": "last_session_sent_size_bytes",
    "F06": "last_session_errors_count",
    "F07": "protected_size_bytes",
    "F08": "color_bar_28_days",
    "F09": "last_successful_session_time",
    "F10": "pre_recent_selected_count",
    "F11": "pre_recent_selected_size_bytes",
    "F12": "session_duration_seconds",
    "F13": "last_session_license_items_count",
    "F14": "retention",
    "F15": "last_session_time",
    "F16": "last_successful_session_status",
    "F17": "last_completed_session_status",
    "F18": "last_completed_session_time",
    "F19": "last_session_verification_data",
    "F20": "last_session_user_mailboxes_count",
    "F21": "last_session_shared_mailboxes_count",
    # Company information
    "I63": "company_name",
    "I64": "address",
    "I65": "zip_code",
    "I66": "country",
    "I67": "city",
    "I68": "phone_number",
    "I69": "fax_number",
    "I70": "contract_name",
    "I71": "group_name",
    "I72": "demo",
    "I73": "edu",
    "I76": "max_allowed_version",
    # Miscellaneous
    "I6": "last_backup_time",
    "I12": "device_group_name",
    "I13": "own_user_name",
    "I20": "external_ips",
    "I22": "dashboard_frequency",
    "I23": "dashboard_language",
    "I34": "anti_crypto_enabled",
    "I38": "archived_size",
    "I40": "activity_description",
    "I41": "hyper_v_vm_count",
    "I42": "esx_vm_count",
    "I43": "encryption_status",
    "I48": "restore_email",
    "I49": "restore_dashboard_frequency",
    "I50": "restore_dashboard_language",
    "I55": "profile_version",
    "I56": "profile",
    "I57": "sku",
    "I58": "sku_previous_month",
    "I59": "account_type",
    "I60": "proxy_type",
    "I62": "most_recent_restore_plugin",
    "I77": "customer_reference",
    "I80": "recovery_testing",
    "I81": "physicality",
    "I82": "has_passphrase",
}

# Columns to request by default for enumerate_devices - covers the most useful fields
DEFAULT_DEVICE_COLUMNS = [
    "I0",   # device_id
    "I1",   # device_name
    "I18",  # computer_name
    "I4",   # creation_date
    "I6",   # last_backup_time
    "I14",  # used_storage_bytes
    "I16",  # os_version
    "I32",  # os_type (1=workstation, 2=server)
    "I78",  # active_data_sources
    "I36",  # storage_status
    "I35",  # lsv_enabled
    "I80",  # recovery_testing
    "F00",  # last_session_status
    "F09",  # last_successful_session_time
    "F06",  # last_session_errors_count
]


def flatten_settings(settings: list[dict] | None) -> dict:
    """
    Convert Cove's Settings array into a flat dict with readable keys.

    Input:  [{"I1": "my-pc"}, {"I14": "1234567"}]
    Output: {"device_name": "my-pc", "used_storage_bytes": "1234567"}

    Unknown codes are passed through as-is.
    """
    if not settings:
        return {}
    result = {}
    for entry in settings:
        for code, value in entry.items():
            key = COLUMN_CODES.get(code, code)
            result[key] = value
    return result


def _unwrap(raw: Any) -> Any:
    """
    Unwrap Cove's double-nested result structure.

    _rpc_call returns body["result"], but many endpoints wrap their actual
    payload in a second "result" key: {"result": [...], "totalStatistics": null}
    """
    if isinstance(raw, dict) and "result" in raw:
        return raw["result"]
    return raw


class CoveClient:
    """
    Cove Data Protection (N-able Backup) API client using JSON-RPC.

    Usage:
        client = CoveClient(username="...", password="...")
        await client.login()
        partners = await client.enumerate_partners(parentPartnerId=2674794)
        devices = await client.enumerate_devices(partner_id=2674794)
    """

    BASE_URL = "https://api.backup.management/jsonapi"

    # Your reseller partner ID - used as the default root for enumeration.
    # Obtained from the login response PartnerId field.
    ROOT_PARTNER_ID = 2674794

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._visa_token: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=60.0,
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def _rpc_call(self, method: str, params: dict | None = None) -> Any:
        """
        Make a JSON-RPC call and return body["result"].

        The visa token is sent as a top-level field on the request body.
        Each response also carries a fresh visa which we capture automatically.
        """
        client = await self._get_client()

        payload: dict = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": str(uuid.uuid4()),
        }

        if self._visa_token:
            payload["visa"] = self._visa_token

        response = await client.post(self.BASE_URL, json=payload)
        if not response.is_success:
            body_text = response.text[:1000] if response.text else ""
            raise Exception(
                f"Cove HTTP {response.status_code} [{method}]: {body_text}"
            )

        body = response.json()

        if "error" in body:
            error = body["error"]
            raise Exception(f"Cove API error [{method}]: {error.get('message', error)}")

        # Refresh visa from every response to keep the chain alive
        if "visa" in body:
            self._visa_token = body["visa"]

        return body.get("result")

    async def login(self) -> None:
        """
        Authenticate and store the visa token.

        The visa is a top-level field on the Login response body, so we handle
        this call directly rather than going through _rpc_call.
        """
        client = await self._get_client()
        payload = {
            "jsonrpc": "2.0",
            "method": "Login",
            "params": {"username": self.username, "password": self.password},
            "id": str(uuid.uuid4()),
        }
        response = await client.post(self.BASE_URL, json=payload)
        if not response.is_success:
            body_text = response.text[:1000] if response.text else ""
            raise Exception(f"Cove HTTP {response.status_code} [Login]: {body_text}")
        body = response.json()

        if "error" in body:
            error = body["error"]
            raise Exception(f"Cove login error: {error.get('message', error)}")

        self._visa_token = body.get("visa")
        if not self._visa_token:
            raise ValueError(
                f"No visa token in login response. Keys returned: {list(body.keys())}"
            )

    async def _ensure_logged_in(self) -> None:
        if not self._visa_token:
            await self.login()

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # -------------------------------------------------------------------------
    # Partners (Customers)
    # -------------------------------------------------------------------------

    async def enumerate_partners(
        self,
        parent_partner_id: int | None = None,
        fields: list[int] | None = None,
        fetch_recursively: bool = True,
    ) -> list[dict]:
        """
        List customer partners under the given parent.

        Args:
            parent_partner_id: Defaults to ROOT_PARTNER_ID (your reseller account).
            fields: Field indices to include. Defaults to [0,1,2,3,4,5] which gives
                    Id, Name, Level, ParentId, State, ServiceType.
            fetch_recursively: Whether to include nested children.

        Returns:
            List of partner dicts with readable keys.
        """
        await self._ensure_logged_in()
        raw = await self._rpc_call("EnumeratePartners", {
            "parentPartnerId": parent_partner_id or self.ROOT_PARTNER_ID,
            "fields": fields if fields is not None else [0, 1, 2, 3, 4, 5],
            "fetchRecursively": fetch_recursively,
        })
        return _unwrap(raw) or []

    async def get_partner(self, partner_id: int) -> dict:
        """Get a specific partner by numeric ID."""
        await self._ensure_logged_in()
        raw = await self._rpc_call("GetPartnerInfoById", {"partnerId": partner_id})
        return _unwrap(raw) or {}

    async def get_partner_by_uid(self, uid: str) -> dict:
        """Get a partner by their UUID (Guid field)."""
        await self._ensure_logged_in()
        raw = await self._rpc_call("GetPartnerInfoByUid", {"partnerUid": uid})
        return _unwrap(raw) or {}

    async def create_customer(
        self,
        name: str,
        parent_partner_id: int | None = None,
    ) -> dict:
        """
        Create a new customer partner.

        Args:
            name: Customer name
            parent_partner_id: Parent partner ID. Defaults to ROOT_PARTNER_ID.

        Returns:
            Created partner dict with Id, Name, etc.
        """
        await self._ensure_logged_in()
        raw = await self._rpc_call("AddPartner", {
            "partnerInfo": {
                "ParentId": parent_partner_id or self.ROOT_PARTNER_ID,
                "Name": name,
                "Level": "EndCustomer",
                "ServiceType": "AllInclusive",
                "State": "InTrial",
                "Country": "US",
            }
        })
        result = _unwrap(raw)
        # AddPartner returns the new partner ID as an int — fetch full info
        if isinstance(result, int):
            return await self.get_partner(result)
        return result or {}

    # -------------------------------------------------------------------------
    # Devices
    # -------------------------------------------------------------------------

    async def enumerate_devices(
        self,
        partner_id: int | None = None,
        columns: list[str] | None = None,
        start: int = 0,
        count: int = 500,
    ) -> list[dict]:
        """
        List backup devices, returning clean dicts with readable field names.

        Uses EnumerateAccountStatistics with the full column code set.
        Settings are flattened from [{code: value}] into {readable_name: value}.

        Args:
            partner_id: Filter to a specific partner. Defaults to ROOT_PARTNER_ID.
            columns: Column codes to fetch. Defaults to DEFAULT_DEVICE_COLUMNS.
            start: Pagination start record.
            count: Max records to return.

        Returns:
            List of device dicts. Each has account_id, partner_id, flags,
            plus all requested columns as readable keys.
        """
        await self._ensure_logged_in()
        raw = await self._rpc_call("EnumerateAccountStatistics", {
            "query": {
                "PartnerId": partner_id or self.ROOT_PARTNER_ID,
                "StartRecordNumber": start,
                "RecordsCount": count,
                "Columns": columns or DEFAULT_DEVICE_COLUMNS,
            }
        })

        records = _unwrap(raw) or []

        devices = []
        for record in records:
            device = {
                "account_id": record.get("AccountId"),
                "partner_id": record.get("PartnerId"),
                "flags": record.get("Flags") or [],
            }
            device.update(flatten_settings(record.get("Settings")))
            devices.append(device)

        return devices

    async def get_device(self, device_id: int) -> dict:
        """Get a specific device by ID."""
        await self._ensure_logged_in()
        raw = await self._rpc_call("GetDeviceInfo", {"deviceId": device_id})
        return _unwrap(raw) or {}

    async def add_device_to_recovery_testing(
        self,
        device_id: int,
        email: str | None = None,
    ) -> dict:
        """Add a device to recovery testing."""
        await self._ensure_logged_in()
        params: dict = {"deviceId": device_id}
        if email:
            params["notificationEmail"] = email
        return await self._rpc_call("EnableRecoveryTesting", params) or {}

    # -------------------------------------------------------------------------
    # Storage Vaults
    # -------------------------------------------------------------------------

    async def enumerate_storage_vaults(self) -> list[dict]:
        """List available storage vaults."""
        await self._ensure_logged_in()
        raw = await self._rpc_call("EnumerateStorageVaults", {})
        return _unwrap(raw) or []


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

async def get_client() -> CoveClient:
    """
    Get a CoveClient configured from the 'Cove Data Protection' Bifrost integration.

    Usage:
        from modules.cove import get_client

        client = await get_client()
        partners = await client.enumerate_partners()
        devices = await client.enumerate_devices()
    """
    from bifrost import integrations

    integration = await integrations.get("Cove Data Protection")
    if not integration:
        raise RuntimeError("Integration 'Cove Data Protection' not found in Bifrost")

    cfg = integration.config or {}
    username = cfg.get("cove_username")
    password = cfg.get("cove_password")

    if not username or not password:
        raise RuntimeError(
            f"Integration 'Cove Data Protection' is missing cove_username or cove_password. "
            f"Found keys: {list(cfg.keys())}"
        )

    return CoveClient(username=username, password=password)
