"""
IT Glue API Client

Python client for interacting with the IT Glue API.
Documentation: https://api.itglue.com/developer/

Authentication uses x-api-key header.
Uses JSON API specification (https://jsonapi.org/).
"""

from typing import Any, Optional
from enum import Enum
import requests


class Region(str, Enum):
    """IT Glue regional endpoints."""
    US = "api.itglue.com"
    EU = "api.eu.itglue.com"
    AU = "api.au.itglue.com"


class ITGlueClient:
    """Client for IT Glue API."""

    def __init__(self, api_key: str, region: Region = Region.US):
        """
        Initialize IT Glue API client.

        Args:
            api_key: IT Glue API key.
            region: API region (US, EU, or AU). Defaults to US.
        """
        self.api_key = api_key
        self.base_url = f"https://{region.value if isinstance(region, Region) else region}"
        self.session = requests.Session()
        self.session.headers.update({
            "x-api-key": api_key,
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json",
        })

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> dict:
        """Make an API request."""
        url = f"{self.base_url}{path}"
        response = self.session.request(
            method=method,
            url=url,
            params=params,
            json=json_body,
        )
        response.raise_for_status()
        if response.content:
            return response.json()
        return {}

    def _paginate(
        self,
        path: str,
        params: Optional[dict] = None,
        page_size: int = 500,
        max_pages: Optional[int] = None,
    ) -> list[dict]:
        """
        Paginate through a list endpoint.

        IT Glue uses page[number] and page[size] for pagination.
        Max page size is 1000.
        """
        params = params or {}
        params["page[size]"] = min(page_size, 1000)
        all_results = []
        page = 1

        while True:
            params["page[number]"] = page
            response = self._request("GET", path, params=params)

            data = response.get("data", [])
            if not data:
                break

            all_results.extend(data)

            # Check pagination metadata
            meta = response.get("meta", {})
            total_pages = meta.get("total-pages", 1)
            page += 1

            if page > total_pages:
                break
            if max_pages and page > max_pages:
                break

        return all_results

    def _build_json_api_body(
        self,
        resource_type: str,
        attributes: dict,
        relationships: Optional[dict] = None,
    ) -> dict:
        """Build a JSON API spec compliant request body."""
        body: dict[str, Any] = {
            "data": {
                "type": resource_type,
                "attributes": attributes,
            }
        }
        if relationships:
            body["data"]["relationships"] = relationships
        return body

    # =========================================================================
    # Organizations
    # =========================================================================

    def list_organizations(
        self,
        *,
        name: Optional[str] = None,
        organization_type_id: Optional[int] = None,
        organization_status_id: Optional[int] = None,
        psa_id: Optional[str] = None,
        filter_id: Optional[int] = None,
        sort: Optional[str] = None,
        paginate: bool = True,
    ) -> list[dict]:
        """
        List organizations.

        Args:
            name: Filter by name (exact match)
            organization_type_id: Filter by organization type
            organization_status_id: Filter by organization status
            psa_id: Filter by PSA ID
            filter_id: Filter by filter preset ID
            sort: Sort field (e.g., 'name', '-updated_at')
            paginate: If True, fetch all pages
        """
        params: dict[str, Any] = {}
        if name:
            params["filter[name]"] = name
        if organization_type_id:
            params["filter[organization_type_id]"] = organization_type_id
        if organization_status_id:
            params["filter[organization_status_id]"] = organization_status_id
        if psa_id:
            params["filter[psa_id]"] = psa_id
        if filter_id:
            params["filter[id]"] = filter_id
        if sort:
            params["sort"] = sort

        if paginate:
            return self._paginate("/organizations", params)
        return self._request("GET", "/organizations", params=params).get("data", [])

    def get_organization(self, organization_id: int) -> dict:
        """Get an organization by ID."""
        response = self._request("GET", f"/organizations/{organization_id}")
        return response.get("data", {})

    def create_organization(
        self,
        *,
        name: str,
        organization_type_id: Optional[int] = None,
        organization_status_id: Optional[int] = None,
        description: Optional[str] = None,
        short_name: Optional[str] = None,
        quick_notes: Optional[str] = None,
        alert: Optional[str] = None,
    ) -> dict:
        """
        Create a new organization.

        Args:
            name: Organization name (required)
            organization_type_id: Organization type ID
            organization_status_id: Organization status ID
            description: Description
            short_name: Short name
            quick_notes: Quick notes
            alert: Alert message
        """
        attributes: dict[str, Any] = {"name": name}
        if organization_type_id:
            attributes["organization-type-id"] = organization_type_id
        if organization_status_id:
            attributes["organization-status-id"] = organization_status_id
        if description:
            attributes["description"] = description
        if short_name:
            attributes["short-name"] = short_name
        if quick_notes:
            attributes["quick-notes"] = quick_notes
        if alert:
            attributes["alert"] = alert

        body = self._build_json_api_body("organizations", attributes)
        response = self._request("POST", "/organizations", json_body=body)
        return response.get("data", {})

    def update_organization(self, organization_id: int, **attributes: Any) -> dict:
        """
        Update an organization.

        Args:
            organization_id: Organization ID
            **attributes: Fields to update (name, description, short_name, etc.)
        """
        # Convert snake_case to kebab-case for JSON API
        converted = {}
        for key, value in attributes.items():
            api_key = key.replace("_", "-")
            converted[api_key] = value

        body = self._build_json_api_body("organizations", converted)
        response = self._request("PATCH", f"/organizations/{organization_id}", json_body=body)
        return response.get("data", {})

    def delete_organization(self, organization_id: int, *, delete_type: str = "trash") -> None:
        """
        Delete an organization.

        Args:
            organization_id: Organization ID
            delete_type: 'trash' (recoverable) or 'hard_delete' (permanent)
        """
        body = self._build_json_api_body("organizations", {"id": organization_id})
        body["data"]["attributes"]["delete-type"] = delete_type
        self._request("DELETE", f"/organizations/{organization_id}", json_body=body)

    # =========================================================================
    # Configurations (Assets)
    # =========================================================================

    def list_configurations(
        self,
        organization_id: Optional[int] = None,
        *,
        name: Optional[str] = None,
        configuration_type_id: Optional[int] = None,
        configuration_status_id: Optional[int] = None,
        serial_number: Optional[str] = None,
        rmm_id: Optional[str] = None,
        psa_id: Optional[str] = None,
        sort: Optional[str] = None,
        include: Optional[str] = None,
        paginate: bool = True,
    ) -> list[dict]:
        """
        List configurations (assets).

        Args:
            organization_id: Filter by organization (use None for all orgs)
            name: Filter by name
            configuration_type_id: Filter by configuration type
            configuration_status_id: Filter by configuration status
            serial_number: Filter by serial number
            rmm_id: Filter by RMM ID
            psa_id: Filter by PSA ID
            sort: Sort field
            include: Related resources to include (comma-separated)
            paginate: If True, fetch all pages
        """
        if organization_id:
            path = f"/organizations/{organization_id}/relationships/configurations"
        else:
            path = "/configurations"

        params: dict[str, Any] = {}
        if name:
            params["filter[name]"] = name
        if configuration_type_id:
            params["filter[configuration_type_id]"] = configuration_type_id
        if configuration_status_id:
            params["filter[configuration_status_id]"] = configuration_status_id
        if serial_number:
            params["filter[serial_number]"] = serial_number
        if rmm_id:
            params["filter[rmm_id]"] = rmm_id
        if psa_id:
            params["filter[psa_id]"] = psa_id
        if sort:
            params["sort"] = sort
        if include:
            params["include"] = include

        if paginate:
            return self._paginate(path, params)
        return self._request("GET", path, params=params).get("data", [])

    def get_configuration(self, configuration_id: int, *, include: Optional[str] = None) -> dict:
        """
        Get a configuration by ID.

        Args:
            configuration_id: Configuration ID
            include: Related resources to include
        """
        params = {}
        if include:
            params["include"] = include
        response = self._request("GET", f"/configurations/{configuration_id}", params=params or None)
        return response.get("data", {})

    def create_configuration(
        self,
        *,
        organization_id: int,
        configuration_type_id: int,
        name: str,
        hostname: Optional[str] = None,
        serial_number: Optional[str] = None,
        asset_tag: Optional[str] = None,
        primary_ip: Optional[str] = None,
        mac_address: Optional[str] = None,
        default_gateway: Optional[str] = None,
        notes: Optional[str] = None,
        configuration_status_id: Optional[int] = None,
        manufacturer_id: Optional[int] = None,
        model_id: Optional[int] = None,
        location_id: Optional[int] = None,
        contact_id: Optional[int] = None,
    ) -> dict:
        """
        Create a new configuration (asset).

        Args:
            organization_id: Organization ID (required)
            configuration_type_id: Configuration type ID (required)
            name: Name (required)
            hostname: Hostname
            serial_number: Serial number
            asset_tag: Asset tag
            primary_ip: Primary IP address
            mac_address: MAC address
            default_gateway: Default gateway
            notes: Notes
            configuration_status_id: Configuration status ID
            manufacturer_id: Manufacturer ID
            model_id: Model ID
            location_id: Location ID
            contact_id: Contact ID
        """
        attributes: dict[str, Any] = {
            "organization-id": organization_id,
            "configuration-type-id": configuration_type_id,
            "name": name,
        }
        if hostname:
            attributes["hostname"] = hostname
        if serial_number:
            attributes["serial-number"] = serial_number
        if asset_tag:
            attributes["asset-tag"] = asset_tag
        if primary_ip:
            attributes["primary-ip"] = primary_ip
        if mac_address:
            attributes["mac-address"] = mac_address
        if default_gateway:
            attributes["default-gateway"] = default_gateway
        if notes:
            attributes["notes"] = notes
        if configuration_status_id:
            attributes["configuration-status-id"] = configuration_status_id
        if manufacturer_id:
            attributes["manufacturer-id"] = manufacturer_id
        if model_id:
            attributes["model-id"] = model_id
        if location_id:
            attributes["location-id"] = location_id
        if contact_id:
            attributes["contact-id"] = contact_id

        body = self._build_json_api_body("configurations", attributes)
        response = self._request("POST", "/configurations", json_body=body)
        return response.get("data", {})

    def update_configuration(self, configuration_id: int, **attributes: Any) -> dict:
        """Update a configuration."""
        converted = {}
        for key, value in attributes.items():
            api_key = key.replace("_", "-")
            converted[api_key] = value

        body = self._build_json_api_body("configurations", converted)
        response = self._request("PATCH", f"/configurations/{configuration_id}", json_body=body)
        return response.get("data", {})

    # =========================================================================
    # Contacts
    # =========================================================================

    def list_contacts(
        self,
        organization_id: Optional[int] = None,
        *,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        title: Optional[str] = None,
        contact_type_id: Optional[int] = None,
        psa_id: Optional[str] = None,
        sort: Optional[str] = None,
        paginate: bool = True,
    ) -> list[dict]:
        """
        List contacts.

        Args:
            organization_id: Filter by organization
            first_name: Filter by first name
            last_name: Filter by last name
            title: Filter by title
            contact_type_id: Filter by contact type
            psa_id: Filter by PSA ID
            sort: Sort field
            paginate: If True, fetch all pages
        """
        if organization_id:
            path = f"/organizations/{organization_id}/relationships/contacts"
        else:
            path = "/contacts"

        params: dict[str, Any] = {}
        if first_name:
            params["filter[first_name]"] = first_name
        if last_name:
            params["filter[last_name]"] = last_name
        if title:
            params["filter[title]"] = title
        if contact_type_id:
            params["filter[contact_type_id]"] = contact_type_id
        if psa_id:
            params["filter[psa_id]"] = psa_id
        if sort:
            params["sort"] = sort

        if paginate:
            return self._paginate(path, params)
        return self._request("GET", path, params=params).get("data", [])

    def get_contact(self, contact_id: int) -> dict:
        """Get a contact by ID."""
        response = self._request("GET", f"/contacts/{contact_id}")
        return response.get("data", {})

    def create_contact(
        self,
        *,
        organization_id: int,
        first_name: str,
        last_name: str,
        title: Optional[str] = None,
        contact_type_id: Optional[int] = None,
        location_id: Optional[int] = None,
        notes: Optional[str] = None,
        important: bool = False,
    ) -> dict:
        """
        Create a new contact.

        Args:
            organization_id: Organization ID (required)
            first_name: First name (required)
            last_name: Last name (required)
            title: Job title
            contact_type_id: Contact type ID
            location_id: Location ID
            notes: Notes
            important: Mark as important contact
        """
        attributes: dict[str, Any] = {
            "organization-id": organization_id,
            "first-name": first_name,
            "last-name": last_name,
        }
        if title:
            attributes["title"] = title
        if contact_type_id:
            attributes["contact-type-id"] = contact_type_id
        if location_id:
            attributes["location-id"] = location_id
        if notes:
            attributes["notes"] = notes
        if important:
            attributes["important"] = important

        body = self._build_json_api_body("contacts", attributes)
        response = self._request("POST", "/contacts", json_body=body)
        return response.get("data", {})

    def update_contact(self, contact_id: int, **attributes: Any) -> dict:
        """Update a contact."""
        converted = {}
        for key, value in attributes.items():
            api_key = key.replace("_", "-")
            converted[api_key] = value

        body = self._build_json_api_body("contacts", converted)
        response = self._request("PATCH", f"/contacts/{contact_id}", json_body=body)
        return response.get("data", {})

    # =========================================================================
    # Passwords
    # =========================================================================

    def list_passwords(
        self,
        organization_id: Optional[int] = None,
        *,
        name: Optional[str] = None,
        password_category_id: Optional[int] = None,
        url: Optional[str] = None,
        cached_resource_name: Optional[str] = None,
        sort: Optional[str] = None,
        paginate: bool = True,
    ) -> list[dict]:
        """
        List passwords.

        Args:
            organization_id: Filter by organization
            name: Filter by name
            password_category_id: Filter by password category
            url: Filter by URL
            cached_resource_name: Filter by cached resource name
            sort: Sort field
            paginate: If True, fetch all pages
        """
        if organization_id:
            path = f"/organizations/{organization_id}/relationships/passwords"
        else:
            path = "/passwords"

        params: dict[str, Any] = {}
        if name:
            params["filter[name]"] = name
        if password_category_id:
            params["filter[password_category_id]"] = password_category_id
        if url:
            params["filter[url]"] = url
        if cached_resource_name:
            params["filter[cached_resource_name]"] = cached_resource_name
        if sort:
            params["sort"] = sort

        if paginate:
            return self._paginate(path, params)
        return self._request("GET", path, params=params).get("data", [])

    def get_password(
        self,
        password_id: int,
        *,
        show_password: bool = True,
    ) -> dict:
        """
        Get a password by ID.

        Args:
            password_id: Password ID
            show_password: Include the password value in response
        """
        params = {"show_password": str(show_password).lower()}
        response = self._request("GET", f"/passwords/{password_id}", params=params)
        return response.get("data", {})

    def create_password(
        self,
        *,
        organization_id: int,
        name: str,
        password: str,
        username: Optional[str] = None,
        url: Optional[str] = None,
        notes: Optional[str] = None,
        password_category_id: Optional[int] = None,
        restricted: bool = False,
        resource_id: Optional[int] = None,
        resource_type: Optional[str] = None,
    ) -> dict:
        """
        Create a new password.

        Args:
            organization_id: Organization ID (required)
            name: Name (required)
            password: Password value (required)
            username: Username
            url: URL
            notes: Notes
            password_category_id: Password category ID
            restricted: Restrict access to password
            resource_id: Resource ID to embed password on (use with resource_type)
            resource_type: Resource type (Configuration, Contact, Document, Domain,
                Location, SSL Certificate, Flexible Asset, Ticket)
        """
        attributes: dict[str, Any] = {
            "organization-id": organization_id,
            "name": name,
            "password": password,
        }
        if username:
            attributes["username"] = username
        if url:
            attributes["url"] = url
        if notes:
            attributes["notes"] = notes
        if password_category_id:
            attributes["password-category-id"] = password_category_id
        if restricted:
            attributes["restricted"] = restricted
        if resource_id is not None and resource_type is not None:
            attributes["resource-id"] = resource_id
            attributes["resource-type"] = resource_type

        body = self._build_json_api_body("passwords", attributes)
        response = self._request("POST", "/passwords", json_body=body)
        return response.get("data", {})

    def update_password(self, password_id: int, **attributes: Any) -> dict:
        """Update a password."""
        converted = {}
        for key, value in attributes.items():
            api_key = key.replace("_", "-")
            converted[api_key] = value

        body = self._build_json_api_body("passwords", converted)
        response = self._request("PATCH", f"/passwords/{password_id}", json_body=body)
        return response.get("data", {})

    def delete_password(self, password_id: int) -> None:
        """Delete a password."""
        self._request("DELETE", f"/passwords/{password_id}")

    # =========================================================================
    # Flexible Assets
    # =========================================================================

    def list_flexible_assets(
        self,
        *,
        flexible_asset_type_id: int,
        organization_id: Optional[int] = None,
        name: Optional[str] = None,
        sort: Optional[str] = None,
        include: Optional[str] = None,
        paginate: bool = True,
    ) -> list[dict]:
        """
        List flexible assets.

        Args:
            flexible_asset_type_id: Flexible asset type ID (required)
            organization_id: Filter by organization
            name: Filter by name
            sort: Sort field
            include: Related resources to include
            paginate: If True, fetch all pages
        """
        params: dict[str, Any] = {
            "filter[flexible_asset_type_id]": flexible_asset_type_id,
        }
        if organization_id:
            params["filter[organization_id]"] = organization_id
        if name:
            params["filter[name]"] = name
        if sort:
            params["sort"] = sort
        if include:
            params["include"] = include

        if paginate:
            return self._paginate("/flexible_assets", params)
        return self._request("GET", "/flexible_assets", params=params).get("data", [])

    def get_flexible_asset(self, flexible_asset_id: int, *, include: Optional[str] = None) -> dict:
        """Get a flexible asset by ID."""
        params = {}
        if include:
            params["include"] = include
        response = self._request("GET", f"/flexible_assets/{flexible_asset_id}", params=params or None)
        return response.get("data", {})

    def create_flexible_asset(
        self,
        *,
        organization_id: int,
        flexible_asset_type_id: int,
        traits: dict,
    ) -> dict:
        """
        Create a new flexible asset.

        Args:
            organization_id: Organization ID (required)
            flexible_asset_type_id: Flexible asset type ID (required)
            traits: Field values for the flexible asset (field names as keys)
        """
        attributes: dict[str, Any] = {
            "organization-id": organization_id,
            "flexible-asset-type-id": flexible_asset_type_id,
            "traits": traits,
        }

        body = self._build_json_api_body("flexible-assets", attributes)
        response = self._request("POST", "/flexible_assets", json_body=body)
        return response.get("data", {})

    def update_flexible_asset(self, flexible_asset_id: int, *, traits: dict) -> dict:
        """
        Update a flexible asset.

        Args:
            flexible_asset_id: Flexible asset ID
            traits: Field values to update
        """
        body = self._build_json_api_body("flexible-assets", {"traits": traits})
        response = self._request("PATCH", f"/flexible_assets/{flexible_asset_id}", json_body=body)
        return response.get("data", {})

    def delete_flexible_asset(self, flexible_asset_id: int) -> None:
        """Delete a flexible asset."""
        self._request("DELETE", f"/flexible_assets/{flexible_asset_id}")

    # =========================================================================
    # Flexible Asset Types
    # =========================================================================

    def list_flexible_asset_types(self, *, paginate: bool = True) -> list[dict]:
        """List all flexible asset types."""
        if paginate:
            return self._paginate("/flexible_asset_types")
        return self._request("GET", "/flexible_asset_types").get("data", [])

    def get_flexible_asset_type(self, flexible_asset_type_id: int) -> dict:
        """Get a flexible asset type by ID."""
        response = self._request("GET", f"/flexible_asset_types/{flexible_asset_type_id}")
        return response.get("data", {})

    # =========================================================================
    # Locations
    # =========================================================================

    def list_locations(
        self,
        organization_id: Optional[int] = None,
        *,
        name: Optional[str] = None,
        city: Optional[str] = None,
        region_id: Optional[int] = None,
        country_id: Optional[int] = None,
        psa_id: Optional[str] = None,
        sort: Optional[str] = None,
        paginate: bool = True,
    ) -> list[dict]:
        """
        List locations.

        Args:
            organization_id: Filter by organization
            name: Filter by name
            city: Filter by city
            region_id: Filter by region
            country_id: Filter by country
            psa_id: Filter by PSA ID
            sort: Sort field
            paginate: If True, fetch all pages
        """
        if organization_id:
            path = f"/organizations/{organization_id}/relationships/locations"
        else:
            path = "/locations"

        params: dict[str, Any] = {}
        if name:
            params["filter[name]"] = name
        if city:
            params["filter[city]"] = city
        if region_id:
            params["filter[region_id]"] = region_id
        if country_id:
            params["filter[country_id]"] = country_id
        if psa_id:
            params["filter[psa_id]"] = psa_id
        if sort:
            params["sort"] = sort

        if paginate:
            return self._paginate(path, params)
        return self._request("GET", path, params=params).get("data", [])

    def get_location(self, location_id: int) -> dict:
        """Get a location by ID."""
        response = self._request("GET", f"/locations/{location_id}")
        return response.get("data", {})

    def create_location(
        self,
        *,
        organization_id: int,
        name: str,
        address_1: Optional[str] = None,
        address_2: Optional[str] = None,
        city: Optional[str] = None,
        postal_code: Optional[str] = None,
        region_id: Optional[int] = None,
        country_id: Optional[int] = None,
        phone: Optional[str] = None,
        fax: Optional[str] = None,
        notes: Optional[str] = None,
        primary: bool = False,
    ) -> dict:
        """Create a new location."""
        attributes: dict[str, Any] = {
            "organization-id": organization_id,
            "name": name,
        }
        if address_1:
            attributes["address-1"] = address_1
        if address_2:
            attributes["address-2"] = address_2
        if city:
            attributes["city"] = city
        if postal_code:
            attributes["postal-code"] = postal_code
        if region_id:
            attributes["region-id"] = region_id
        if country_id:
            attributes["country-id"] = country_id
        if phone:
            attributes["phone"] = phone
        if fax:
            attributes["fax"] = fax
        if notes:
            attributes["notes"] = notes
        if primary:
            attributes["primary"] = primary

        body = self._build_json_api_body("locations", attributes)
        response = self._request("POST", "/locations", json_body=body)
        return response.get("data", {})

    def update_location(self, location_id: int, **attributes: Any) -> dict:
        """Update a location."""
        converted = {}
        for key, value in attributes.items():
            api_key = key.replace("_", "-")
            converted[api_key] = value

        body = self._build_json_api_body("locations", converted)
        response = self._request("PATCH", f"/locations/{location_id}", json_body=body)
        return response.get("data", {})

    def delete_location(self, location_id: int) -> None:
        """Delete a location."""
        self._request("DELETE", f"/locations/{location_id}")

    # =========================================================================
    # Configuration Types
    # =========================================================================

    def list_configuration_types(self, *, paginate: bool = True) -> list[dict]:
        """List all configuration types."""
        if paginate:
            return self._paginate("/configuration_types")
        return self._request("GET", "/configuration_types").get("data", [])

    def get_configuration_type(self, configuration_type_id: int) -> dict:
        """Get a configuration type by ID."""
        response = self._request("GET", f"/configuration_types/{configuration_type_id}")
        return response.get("data", {})

    # =========================================================================
    # Configuration Statuses
    # =========================================================================

    def list_configuration_statuses(self, *, paginate: bool = True) -> list[dict]:
        """List all configuration statuses."""
        if paginate:
            return self._paginate("/configuration_statuses")
        return self._request("GET", "/configuration_statuses").get("data", [])

    def get_configuration_status(self, configuration_status_id: int) -> dict:
        """Get a configuration status by ID."""
        response = self._request("GET", f"/configuration_statuses/{configuration_status_id}")
        return response.get("data", {})

    # =========================================================================
    # Organization Types
    # =========================================================================

    def list_organization_types(self, *, paginate: bool = True) -> list[dict]:
        """List all organization types."""
        if paginate:
            return self._paginate("/organization_types")
        return self._request("GET", "/organization_types").get("data", [])

    def get_organization_type(self, organization_type_id: int) -> dict:
        """Get an organization type by ID."""
        response = self._request("GET", f"/organization_types/{organization_type_id}")
        return response.get("data", {})

    # =========================================================================
    # Organization Statuses
    # =========================================================================

    def list_organization_statuses(self, *, paginate: bool = True) -> list[dict]:
        """List all organization statuses."""
        if paginate:
            return self._paginate("/organization_statuses")
        return self._request("GET", "/organization_statuses").get("data", [])

    def get_organization_status(self, organization_status_id: int) -> dict:
        """Get an organization status by ID."""
        response = self._request("GET", f"/organization_statuses/{organization_status_id}")
        return response.get("data", {})

    # =========================================================================
    # Contact Types
    # =========================================================================

    def list_contact_types(self, *, paginate: bool = True) -> list[dict]:
        """List all contact types."""
        if paginate:
            return self._paginate("/contact_types")
        return self._request("GET", "/contact_types").get("data", [])

    def get_contact_type(self, contact_type_id: int) -> dict:
        """Get a contact type by ID."""
        response = self._request("GET", f"/contact_types/{contact_type_id}")
        return response.get("data", {})

    # =========================================================================
    # Password Categories
    # =========================================================================

    def list_password_categories(self, *, paginate: bool = True) -> list[dict]:
        """List all password categories."""
        if paginate:
            return self._paginate("/password_categories")
        return self._request("GET", "/password_categories").get("data", [])

    def get_password_category(self, password_category_id: int) -> dict:
        """Get a password category by ID."""
        response = self._request("GET", f"/password_categories/{password_category_id}")
        return response.get("data", {})

    # =========================================================================
    # Manufacturers
    # =========================================================================

    def list_manufacturers(self, *, name: Optional[str] = None, paginate: bool = True) -> list[dict]:
        """List manufacturers."""
        params: dict[str, Any] = {}
        if name:
            params["filter[name]"] = name
        if paginate:
            return self._paginate("/manufacturers", params)
        return self._request("GET", "/manufacturers", params=params or None).get("data", [])

    def get_manufacturer(self, manufacturer_id: int) -> dict:
        """Get a manufacturer by ID."""
        response = self._request("GET", f"/manufacturers/{manufacturer_id}")
        return response.get("data", {})

    # =========================================================================
    # Models
    # =========================================================================

    def list_models(
        self,
        *,
        manufacturer_id: Optional[int] = None,
        paginate: bool = True,
    ) -> list[dict]:
        """List models."""
        params: dict[str, Any] = {}
        if manufacturer_id:
            params["filter[manufacturer_id]"] = manufacturer_id
        if paginate:
            return self._paginate("/models", params)
        return self._request("GET", "/models", params=params or None).get("data", [])

    def get_model(self, model_id: int) -> dict:
        """Get a model by ID."""
        response = self._request("GET", f"/models/{model_id}")
        return response.get("data", {})

    # =========================================================================
    # Operating Systems
    # =========================================================================

    def list_operating_systems(self, *, name: Optional[str] = None, paginate: bool = True) -> list[dict]:
        """List operating systems."""
        params: dict[str, Any] = {}
        if name:
            params["filter[name]"] = name
        if paginate:
            return self._paginate("/operating_systems", params)
        return self._request("GET", "/operating_systems", params=params or None).get("data", [])

    def get_operating_system(self, operating_system_id: int) -> dict:
        """Get an operating system by ID."""
        response = self._request("GET", f"/operating_systems/{operating_system_id}")
        return response.get("data", {})

    # =========================================================================
    # Countries & Regions
    # =========================================================================

    def list_countries(self, *, name: Optional[str] = None, paginate: bool = True) -> list[dict]:
        """List countries."""
        params: dict[str, Any] = {}
        if name:
            params["filter[name]"] = name
        if paginate:
            return self._paginate("/countries", params)
        return self._request("GET", "/countries", params=params or None).get("data", [])

    def get_country(self, country_id: int) -> dict:
        """Get a country by ID."""
        response = self._request("GET", f"/countries/{country_id}")
        return response.get("data", {})

    def list_regions(
        self,
        *,
        country_id: Optional[int] = None,
        name: Optional[str] = None,
        paginate: bool = True,
    ) -> list[dict]:
        """List regions."""
        params: dict[str, Any] = {}
        if country_id:
            params["filter[country_id]"] = country_id
        if name:
            params["filter[name]"] = name
        if paginate:
            return self._paginate("/regions", params)
        return self._request("GET", "/regions", params=params or None).get("data", [])

    def get_region(self, region_id: int) -> dict:
        """Get a region by ID."""
        response = self._request("GET", f"/regions/{region_id}")
        return response.get("data", {})

    # =========================================================================
    # Users & Groups
    # =========================================================================

    def list_users(self, *, paginate: bool = True) -> list[dict]:
        """List users."""
        if paginate:
            return self._paginate("/users")
        return self._request("GET", "/users").get("data", [])

    def get_user(self, user_id: int) -> dict:
        """Get the accounts user info."""
        response = self._request("GET", f"/users/{user_id}")
        return response.get("data", {})

    def list_groups(self, *, name: Optional[str] = None, paginate: bool = True) -> list[dict]:
        """List groups."""
        params: dict[str, Any] = {}
        if name:
            params["filter[name]"] = name
        if paginate:
            return self._paginate("/groups", params)
        return self._request("GET", "/groups", params=params or None).get("data", [])

    def get_group(self, group_id: int) -> dict:
        """Get a group by ID."""
        response = self._request("GET", f"/groups/{group_id}")
        return response.get("data", {})

    # =========================================================================
    # Domains & Expirations
    # =========================================================================

    def list_domains(
        self,
        organization_id: Optional[int] = None,
        *,
        paginate: bool = True,
    ) -> list[dict]:
        """List domains."""
        if organization_id:
            path = f"/organizations/{organization_id}/relationships/domains"
        else:
            path = "/domains"
        if paginate:
            return self._paginate(path)
        return self._request("GET", path).get("data", [])

    def list_expirations(
        self,
        organization_id: Optional[int] = None,
        *,
        paginate: bool = True,
    ) -> list[dict]:
        """List expirations."""
        if organization_id:
            path = f"/organizations/{organization_id}/relationships/expirations"
        else:
            path = "/expirations"
        if paginate:
            return self._paginate(path)
        return self._request("GET", path).get("data", [])

    # =========================================================================
    # Related Items
    # =========================================================================

    def create_related_item(
        self,
        *,
        source_type: str,
        source_id: int,
        destination_type: str,
        destination_id: int,
        notes: Optional[str] = None,
    ) -> dict:
        """
        Create a relationship between two items.

        Args:
            source_type: Source resource type (e.g., 'Configuration', 'Contact')
            source_id: Source resource ID
            destination_type: Destination resource type
            destination_id: Destination resource ID
            notes: Optional notes about the relationship
        """
        attributes: dict[str, Any] = {
            "source-type": source_type,
            "source-id": source_id,
            "destination-type": destination_type,
            "destination-id": destination_id,
        }
        if notes:
            attributes["notes"] = notes

        body = self._build_json_api_body("related_items", attributes)
        response = self._request("POST", "/related_items", json_body=body)
        return response.get("data", {})

    def delete_related_item(
        self,
        *,
        source_type: str,
        source_id: int,
        destination_type: str,
        destination_id: int,
    ) -> None:
        """Delete a relationship between two items."""
        # The delete endpoint requires POST with the relationship details
        attributes = {
            "source-type": source_type,
            "source-id": source_id,
            "destination-type": destination_type,
            "destination-id": destination_id,
        }
        body = self._build_json_api_body("related_items", attributes)
        # Use a specific endpoint format for deletion
        path = f"/related_items?source_type={source_type}&source_id={source_id}&destination_type={destination_type}&destination_id={destination_id}"
        self._request("DELETE", path, json_body=body)

    # =========================================================================
    # Logs
    # =========================================================================

    def list_logs(
        self,
        *,
        created_at_start: Optional[str] = None,
        created_at_end: Optional[str] = None,
        paginate: bool = True,
    ) -> list[dict]:
        """
        List activity logs.

        Args:
            created_at_start: Filter by start date (ISO 8601)
            created_at_end: Filter by end date (ISO 8601)
            paginate: If True, fetch all pages
        """
        params: dict[str, Any] = {}
        if created_at_start:
            params["filter[created_at][start]"] = created_at_start
        if created_at_end:
            params["filter[created_at][end]"] = created_at_end
        if paginate:
            return self._paginate("/logs", params)
        return self._request("GET", "/logs", params=params or None).get("data", [])

    # =========================================================================
    # Generic Request (for endpoints not yet implemented)
    # =========================================================================

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> dict:
        """
        Make a generic API request.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            path: API path (e.g., '/organizations')
            params: Query parameters
            json_body: JSON body for POST/PATCH requests
        """
        return self._request(method, path, params=params, json_body=json_body)


def create_client(api_key: str, region: Region | str = Region.US) -> ITGlueClient:
    """
    Create an IT Glue client.

    Usage:
        from modules.itglue import create_client, Region

        api_key = await secrets.get("itglue_api_key")
        client = create_client(api_key)
        orgs = client.list_organizations()

        # For EU region:
        client = create_client(api_key, region=Region.EU)

    Args:
        api_key: IT Glue API key
        region: API region (US, EU, or AU). Defaults to US.

    Returns:
        Configured ITGlueClient instance
    """
    if isinstance(region, str):
        region = Region(region)
    return ITGlueClient(api_key, region)


# =============================================================================
# Lazy Client (Bifrost Integration)
# =============================================================================


class _LazyClient:
    """
    Module-level proxy that auto-initializes from Bifrost integration.
    Provides zero-config authentication — just ``await itglue.list_organizations()``.

    Note: Client is NOT cached — always fetches fresh credentials.
    """

    _integration_name: str = "IT Glue"

    async def _ensure_client(self) -> ITGlueClient:
        from bifrost import integrations

        integration = await integrations.get(self._integration_name)
        if not integration:
            raise RuntimeError(f"Integration '{self._integration_name}' not found")

        config = integration.config or {}
        api_key = config.get("api_key")
        if not api_key:
            raise RuntimeError(
                f"api_key not configured for integration '{self._integration_name}'"
            )

        region_name = config.get("region", "US")
        try:
            region = Region[region_name]
        except KeyError:
            region = Region.US
        return create_client(api_key, region=region)

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
