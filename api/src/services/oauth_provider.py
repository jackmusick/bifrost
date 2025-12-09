"""
OAuth Provider Client
Handles HTTP communication with OAuth providers for token exchange and refresh
"""

import asyncio
import logging
from datetime import datetime, timedelta

import aiohttp

logger = logging.getLogger(__name__)


class OAuthProviderClient:
    """
    Client for interacting with OAuth 2.0 providers

    Features:
    - Token exchange (authorization code → access token)
    - Token refresh (refresh token → new access token)
    - Client credentials flow
    - Retry logic with exponential backoff
    - Timeout handling
    """

    def __init__(self, timeout: int = 10, max_retries: int = 3):
        """
        Initialize OAuth provider client

        Args:
            timeout: Request timeout in seconds (default: 10)
            max_retries: Maximum number of retry attempts (default: 3)
        """
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        logger.debug(f"OAuthProviderClient initialized (timeout={timeout}s, max_retries={max_retries})")

    async def exchange_code_for_token(
        self,
        token_url: str,
        code: str,
        client_id: str,
        client_secret: str | None,
        redirect_uri: str
    ) -> tuple[bool, dict]:
        """
        Exchange authorization code for access token (authorization code flow)

        Args:
            token_url: OAuth provider's token endpoint
            code: Authorization code from OAuth callback
            client_id: OAuth client ID
            client_secret: OAuth client secret (optional, omit for PKCE flow)
            redirect_uri: Redirect URI used in authorization request

        Returns:
            Tuple of (success, result_dict)
            - If success: result_dict contains token data
            - If failure: result_dict contains error information
        """
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": redirect_uri
        }

        # Only include client_secret if provided (PKCE flow omits this)
        if client_secret:
            payload["client_secret"] = client_secret
            logger.info(f"Exchanging authorization code for token at {token_url} (with client_secret)")
        else:
            logger.info(f"Exchanging authorization code for token at {token_url} (PKCE flow - no client_secret)")

        return await self._make_token_request(token_url, payload)

    async def refresh_access_token(
        self,
        token_url: str,
        refresh_token: str,
        client_id: str,
        client_secret: str | None
    ) -> tuple[bool, dict]:
        """
        Refresh access token using refresh token

        Args:
            token_url: OAuth provider's token endpoint
            refresh_token: Refresh token
            client_id: OAuth client ID
            client_secret: OAuth client secret (optional, omit for PKCE flow)

        Returns:
            Tuple of (success, result_dict)
        """
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id
        }

        # Only include client_secret if provided (PKCE flow omits this)
        if client_secret:
            payload["client_secret"] = client_secret
            logger.info(f"Refreshing access token at {token_url} (with client_secret)")
        else:
            logger.info(f"Refreshing access token at {token_url} (PKCE flow - no client_secret)")

        return await self._make_token_request(token_url, payload)

    async def get_client_credentials_token(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        scopes: str = ""
    ) -> tuple[bool, dict]:
        """
        Get token using client credentials flow (service-to-service)

        Args:
            token_url: OAuth provider's token endpoint
            client_id: OAuth client ID
            client_secret: OAuth client secret
            scopes: Space or comma-separated list of scopes

        Returns:
            Tuple of (success, result_dict)
        """
        payload = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret
        }

        if scopes:
            # Normalize scopes to space-separated (OAuth 2.0 standard)
            payload["scope"] = scopes.replace(",", " ")

        logger.info(f"Requesting client credentials token at {token_url}")

        return await self._make_token_request(token_url, payload)

    async def _make_token_request(
        self,
        token_url: str,
        payload: dict
    ) -> tuple[bool, dict]:
        """
        Make token request with retry logic

        Args:
            token_url: Token endpoint URL
            payload: Request payload

        Returns:
            Tuple of (success, result_dict)
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                # Create connector with proper cleanup settings
                connector = aiohttp.TCPConnector(force_close=True)
                async with aiohttp.ClientSession(timeout=self.timeout, connector=connector) as session:
                    async with session.post(
                        token_url,
                        data=payload,
                        headers={"Content-Type": "application/x-www-form-urlencoded"}
                    ) as response:
                        response_data = await response.json()

                        # Success (2xx status codes)
                        if 200 <= response.status < 300:
                            logger.info(f"Token request successful (status={response.status})")
                            logger.debug(f"Raw OAuth response: {response_data}")

                            # Parse token response
                            result = self._parse_token_response(response_data)
                            return (True, result)

                        # Client errors (4xx) - don't retry
                        elif 400 <= response.status < 500:
                            error_msg = response_data.get("error_description") or response_data.get("error") or f"HTTP {response.status}"
                            logger.error(f"Token request failed with client error: {error_msg}")
                            return (False, {
                                "error": response_data.get("error", "client_error"),
                                "error_description": error_msg,
                                "status_code": response.status
                            })

                        # Server errors (5xx) - retry
                        else:
                            error_msg = f"Server error: HTTP {response.status}"
                            logger.warning(f"Token request failed: {error_msg} (attempt {attempt + 1}/{self.max_retries})")
                            last_error = error_msg

                            if attempt < self.max_retries - 1:
                                # Exponential backoff: 1s, 2s, 4s
                                wait_time = 2 ** attempt
                                await asyncio.sleep(wait_time)
                                continue

            except aiohttp.ClientError as e:
                logger.warning(f"Network error during token request: {str(e)} (attempt {attempt + 1}/{self.max_retries})")
                last_error = str(e)

                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                    continue

            except TimeoutError:
                logger.warning(f"Token request timed out (attempt {attempt + 1}/{self.max_retries})")
                last_error = "Request timed out"

                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                    continue

            except Exception as e:
                logger.error(f"Unexpected error during token request: {str(e)}", exc_info=True)
                return (False, {
                    "error": "unexpected_error",
                    "error_description": str(e)
                })

        # All retries exhausted
        logger.error(f"Token request failed after {self.max_retries} attempts: {last_error}")
        return (False, {
            "error": "max_retries_exceeded",
            "error_description": f"Failed after {self.max_retries} attempts: {last_error}"
        })

    def _parse_token_response(self, response_data: dict) -> dict:
        """
        Parse OAuth token response and calculate expiration

        Args:
            response_data: Response JSON from OAuth provider

        Returns:
            Parsed token data with expires_at datetime
        """
        result = {
            "access_token": response_data.get("access_token"),
            "token_type": response_data.get("token_type", "Bearer"),
            "refresh_token": response_data.get("refresh_token"),
            "scope": response_data.get("scope", "")
        }

        # Calculate expires_at from expires_in (seconds)
        expires_in = response_data.get("expires_in")
        if expires_in:
            result["expires_at"] = datetime.utcnow() + timedelta(seconds=int(expires_in))
        else:
            # Default to 1 hour if not specified
            logger.warning("OAuth response missing expires_in, defaulting to 1 hour")
            result["expires_at"] = datetime.utcnow() + timedelta(hours=1)

        # Log refresh token presence at INFO level for debugging
        if result['refresh_token'] is not None:
            logger.info("✓ Token response includes refresh_token")
        else:
            logger.info("✗ Token response does NOT include refresh_token (will use fallback if available)")

        logger.debug(f"Parsed token response: expires_at={result['expires_at']}, has_refresh={result['refresh_token'] is not None}")

        return result
