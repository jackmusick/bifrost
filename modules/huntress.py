"""
Simple Python client for Huntress API Reference

Auto-generated from OpenAPI spec.
Integration: Huntress
Auth Type: apikey (HTTP Basic Auth - api_key:api_secret)
"""

from __future__ import annotations
from typing import Any, Dict
import requests


# Helper class for dot notation access on dicts
class DotDict(dict):
    """Dict subclass that allows dot notation access to keys."""
    def __getattr__(self, key):
        try:
            value = self[key]
            # Recursively convert nested dicts
            if isinstance(value, dict) and not isinstance(value, DotDict):
                return DotDict(value)
            elif isinstance(value, list):
                return [DotDict(item) if isinstance(item, dict) else item for item in value]
            return value
        except KeyError:
            raise AttributeError(f"No attribute {key}")
    
    def __setattr__(self, key, value):
        self[key] = value
    
    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError:
            raise AttributeError(f"No attribute {key}")


# Data Models


class HuntressAPIReference:
    """Simple client for Huntress API Reference."""

    def __init__(self, base_url: str, session: requests.Session = None):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()

    def _auto_convert(self, data):
        """Automatically convert dicts to dataclass objects."""
        if data is None:
            return None
        
        # Handle lists
        if isinstance(data, list):
            return [self._auto_convert(item) for item in data]
        
        # Handle dicts - try to convert to dataclass
        if isinstance(data, dict):
            # Try to find a matching dataclass by checking common fields
            # This is a best-effort approach
            return DotDict(data)
        
        return data

    def list_accounts(self, **kwargs) -> Any:
        """Get Account"""
        url = f"{self.base_url}/v1/account"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def list_accounts_1(self, **kwargs) -> Any:
        """List Accounts"""
        url = f"{self.base_url}/v1/accounts"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_accounts(self, account_id: str, **kwargs) -> Any:
        """Get Specific Account"""
        url = f"{self.base_url}/v1/accounts/{account_id}"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_agents(self, account_id: str, **kwargs) -> Any:
        """List Agents"""
        url = f"{self.base_url}/v1/accounts/{account_id}/agents"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_agents_1(self, account_id: str, id: str, **kwargs) -> Any:
        """Get Agent"""
        url = f"{self.base_url}/v1/accounts/{account_id}/agents/{id}"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_billing_reports(self, account_id: str, **kwargs) -> Any:
        """List Billing Reports"""
        url = f"{self.base_url}/v1/accounts/{account_id}/billing_reports"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_billing_reports_1(self, account_id: str, id: str, **kwargs) -> Any:
        """Get Billing Report"""
        url = f"{self.base_url}/v1/accounts/{account_id}/billing_reports/{id}"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_incident_reports(self, account_id: str, **kwargs) -> Any:
        """List Incident Reports"""
        url = f"{self.base_url}/v1/accounts/{account_id}/incident_reports"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_incident_reports_1(self, account_id: str, id: str, **kwargs) -> Any:
        """Get Incident Report"""
        url = f"{self.base_url}/v1/accounts/{account_id}/incident_reports/{id}"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def create_resolution(self, account_id: str, id: str, data: Dict[str, Any] = None, **kwargs) -> Any:
        """Create an Incident Report Resolution"""
        url = f"{self.base_url}/v1/accounts/{account_id}/incident_reports/{id}/resolution"
        response = self.session.post(url, json=data, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_remediations(self, account_id: str, incident_report_id: str, **kwargs) -> Any:
        """List Remediations"""
        url = f"{self.base_url}/v1/accounts/{account_id}/incident_reports/{incident_report_id}/remediations"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def create_bulk_approval(self, account_id: str, incident_report_id: str, data: Dict[str, Any] = None, **kwargs) -> Any:
        """Bulk Approve Remediations"""
        url = f"{self.base_url}/v1/accounts/{account_id}/incident_reports/{incident_report_id}/remediations/bulk_approval"
        response = self.session.post(url, json=data, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def create_bulk_rejection(self, account_id: str, incident_report_id: str, data: Dict[str, Any] = None, **kwargs) -> Any:
        """Bulk Reject Remediations"""
        url = f"{self.base_url}/v1/accounts/{account_id}/incident_reports/{incident_report_id}/remediations/bulk_rejection"
        response = self.session.post(url, json=data, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_remediations_1(self, account_id: str, incident_report_id: str, remediation_id: str, **kwargs) -> Any:
        """Get Remediation"""
        url = f"{self.base_url}/v1/accounts/{account_id}/incident_reports/{incident_report_id}/remediations/{remediation_id}"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_organizations(self, account_id: str, **kwargs) -> Any:
        """List Organizations"""
        url = f"{self.base_url}/v1/accounts/{account_id}/organizations"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_organizations_1(self, account_id: str, id: str, **kwargs) -> Any:
        """Get Organization"""
        url = f"{self.base_url}/v1/accounts/{account_id}/organizations/{id}"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_reports(self, account_id: str, **kwargs) -> Any:
        """List Summary Reports"""
        url = f"{self.base_url}/v1/accounts/{account_id}/reports"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_reports_1(self, account_id: str, id: str, **kwargs) -> Any:
        """Get Summary Report"""
        url = f"{self.base_url}/v1/accounts/{account_id}/reports/{id}"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_signals(self, account_id: str, **kwargs) -> Any:
        """List Signals"""
        url = f"{self.base_url}/v1/accounts/{account_id}/signals"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_signals_1(self, account_id: str, id: str, **kwargs) -> Any:
        """Get Signal"""
        url = f"{self.base_url}/v1/accounts/{account_id}/signals/{id}"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def list_actors(self, **kwargs) -> Any:
        """Get Actor"""
        url = f"{self.base_url}/v1/actor"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def list_agents(self, **kwargs) -> Any:
        """List Agents"""
        url = f"{self.base_url}/v1/agents"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_agents_2(self, id: str, **kwargs) -> Any:
        """Get Agent"""
        url = f"{self.base_url}/v1/agents/{id}"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def list_billing_reports(self, **kwargs) -> Any:
        """List Billing Reports"""
        url = f"{self.base_url}/v1/billing_reports"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_billing_reports_2(self, id: str, **kwargs) -> Any:
        """Get Billing Report"""
        url = f"{self.base_url}/v1/billing_reports/{id}"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def list_escalations(self, **kwargs) -> Any:
        """List Escalations"""
        url = f"{self.base_url}/v1/escalations"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_escalations(self, id: str, **kwargs) -> Any:
        """Get Escalation"""
        url = f"{self.base_url}/v1/escalations/{id}"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def create_resolution_1(self, id: str, data: Dict[str, Any] = None, **kwargs) -> Any:
        """Create an Escalation Resolution"""
        url = f"{self.base_url}/v1/escalations/{id}/resolution"
        response = self.session.post(url, json=data, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def list_incident_reports(self, **kwargs) -> Any:
        """List Incident Reports"""
        url = f"{self.base_url}/v1/incident_reports"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_incident_reports_2(self, id: str, **kwargs) -> Any:
        """Get Incident Report"""
        url = f"{self.base_url}/v1/incident_reports/{id}"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def create_resolution_2(self, id: str, data: Dict[str, Any] = None, **kwargs) -> Any:
        """Create an Incident Report Resolution"""
        url = f"{self.base_url}/v1/incident_reports/{id}/resolution"
        response = self.session.post(url, json=data, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_remediations_2(self, incident_report_id: str, **kwargs) -> Any:
        """List Remediations"""
        url = f"{self.base_url}/v1/incident_reports/{incident_report_id}/remediations"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def create_bulk_approval_1(self, incident_report_id: str, data: Dict[str, Any] = None, **kwargs) -> Any:
        """Bulk Approve Remediations"""
        url = f"{self.base_url}/v1/incident_reports/{incident_report_id}/remediations/bulk_approval"
        response = self.session.post(url, json=data, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def create_bulk_rejection_1(self, incident_report_id: str, data: Dict[str, Any] = None, **kwargs) -> Any:
        """Bulk Reject Remediations"""
        url = f"{self.base_url}/v1/incident_reports/{incident_report_id}/remediations/bulk_rejection"
        response = self.session.post(url, json=data, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_remediations_3(self, incident_report_id: str, remediation_id: str, **kwargs) -> Any:
        """Get Remediation"""
        url = f"{self.base_url}/v1/incident_reports/{incident_report_id}/remediations/{remediation_id}"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def list_organizations(self, **kwargs) -> Any:
        """List Organizations"""
        url = f"{self.base_url}/v1/organizations"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_organizations_2(self, id: str, **kwargs) -> Any:
        """Get Organization"""
        url = f"{self.base_url}/v1/organizations/{id}"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def list_reports(self, **kwargs) -> Any:
        """List Summary Reports"""
        url = f"{self.base_url}/v1/reports"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_reports_2(self, id: str, **kwargs) -> Any:
        """Get Summary Report"""
        url = f"{self.base_url}/v1/reports/{id}"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def list_signals(self, **kwargs) -> Any:
        """List Signals"""
        url = f"{self.base_url}/v1/signals"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)


    def get_signals_2(self, id: str, **kwargs) -> Any:
        """Get Signal"""
        url = f"{self.base_url}/v1/signals/{id}"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        result = response.json() if response.content else None
        return self._auto_convert(result)



# Convenience alias for imports
client = HuntressAPIReference


# =============================================================================
# Lazy Client (Bifrost Integration)
# =============================================================================


class _LazyClient:
    """
    Module-level proxy that auto-initializes from Bifrost integration.
    Pulls api_key and api_secret from integration config and uses HTTP Basic Auth.

    Note: Client is NOT cached - always fetches fresh credentials.
    """

    _integration_name: str = "Huntress"

    async def _ensure_client(self):
        from bifrost import integrations

        integration = await integrations.get(self._integration_name)
        if not integration:
            raise RuntimeError(f"Integration '{self._integration_name}' not found")

        config = integration.config or {}

        api_key = config.get("api_key")
        api_secret = config.get("api_secret")
        if not api_key or not api_secret:
            raise RuntimeError(
                f"Integration '{self._integration_name}' is missing api_key or api_secret in config"
            )

        base_url = config.get("base_url", "https://api.huntress.io")

        session = requests.Session()
        session.auth = (api_key, api_secret)  # requests encodes as Basic Auth automatically

        return HuntressAPIReference(base_url, session)

    def __getattr__(self, name: str):
        """Proxy attribute access to the real client."""
        async def method_wrapper(*args, **kwargs):
            client = await self._ensure_client()
            method = getattr(client, name)
            return method(*args, **kwargs)
        return method_wrapper


# =============================================================================
# Module-level API
# =============================================================================


# Module-level lazy client instance
_lazy = _LazyClient()


def __getattr__(name: str):
    """Enable module-level attribute access to lazy client methods."""
    return getattr(_lazy, name)
