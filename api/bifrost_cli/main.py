"""
Bifrost CLI

Command-line interface for the Bifrost SDK.

Commands:
  bifrost login   - Authenticate with device authorization flow
  bifrost logout  - Clear stored credentials

Note: This module is standalone and doesn't import the main bifrost package
to avoid dependencies on src.* modules that only exist in the Docker environment.
"""

import asyncio
import os
import sys
import webbrowser
from datetime import datetime, timedelta, timezone

import httpx

# Import credentials module from same package
from . import credentials


async def refresh_tokens() -> bool:
    """
    Refresh access token using refresh token.

    Uses credentials from credentials file.
    Updates credentials file with new tokens.

    Returns:
        True if refresh successful, False otherwise
    """
    creds = credentials.get_credentials()
    if not creds:
        return False

    api_url = creds["api_url"]
    refresh_token = creds["refresh_token"]

    try:
        async with httpx.AsyncClient(base_url=api_url, timeout=30.0) as client:
            response = await client.post(
                "/auth/refresh",
                json={"refresh_token": refresh_token}
            )

            if response.status_code != 200:
                return False

            data = response.json()

            # Calculate expiry time (30 minutes from now)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 1800))

            # Save new credentials
            credentials.save_credentials(
                api_url=api_url,
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                expires_at=expires_at.isoformat(),
            )

            return True
    except Exception:
        return False


async def login_flow(api_url: str | None = None, auto_open: bool = True) -> bool:
    """
    Interactive device authorization flow.

    1. Request device code from API
    2. Display user code and verification URL
    3. Open browser automatically (if auto_open=True)
    4. Poll for authorization
    5. Save credentials when authorized

    Args:
        api_url: Bifrost API URL (uses BIFROST_DEV_URL env var if not provided)
        auto_open: Whether to automatically open browser (default: True)

    Returns:
        True if login successful, False otherwise
    """
    # Get API URL
    if not api_url:
        api_url = os.getenv("BIFROST_DEV_URL", "http://localhost:8000")

    api_url = api_url.rstrip("/")

    try:
        async with httpx.AsyncClient(base_url=api_url, timeout=30.0) as client:
            # Step 1: Request device code
            response = await client.post("/auth/device/code")
            if response.status_code != 200:
                print(f"Error requesting device code: {response.status_code}", file=sys.stderr)
                return False

            data = response.json()
            device_code = data["device_code"]
            user_code = data["user_code"]
            verification_url = data["verification_url"]
            interval = data.get("interval", 5)

            # Step 2: Display instructions
            full_url = f"{api_url}{verification_url}"
            print(f"\nOpening browser to {full_url}")
            print(f"Enter this code: {user_code}\n")

            # Step 3: Open browser
            if auto_open:
                try:
                    webbrowser.open(full_url)
                except Exception:
                    pass  # Ignore browser open failures

            # Step 4: Poll for authorization
            print("Waiting for authorization", end="", flush=True)
            max_attempts = 60  # 5 minutes max (60 * 5 seconds)
            attempts = 0

            while attempts < max_attempts:
                await asyncio.sleep(interval)
                print(".", end="", flush=True)
                attempts += 1

                poll_response = await client.post(
                    "/auth/device/token",
                    json={"device_code": device_code}
                )

                if poll_response.status_code != 200:
                    print(f"\nError polling for token: {poll_response.status_code}", file=sys.stderr)
                    return False

                poll_data = poll_response.json()

                # Check for error
                if "error" in poll_data:
                    error = poll_data["error"]
                    if error == "authorization_pending":
                        continue  # Keep polling
                    elif error == "expired_token":
                        print("\nDevice code expired. Please try again.", file=sys.stderr)
                        return False
                    elif error == "access_denied":
                        print("\nAuthorization denied.", file=sys.stderr)
                        return False
                    else:
                        print(f"\nUnknown error: {error}", file=sys.stderr)
                        return False

                # Success - we have tokens
                if "access_token" in poll_data:
                    print(" OK")

                    # Calculate expiry time
                    expires_at = datetime.now(timezone.utc) + timedelta(seconds=poll_data.get("expires_in", 1800))

                    # Step 5: Save credentials
                    credentials.save_credentials(
                        api_url=api_url,
                        access_token=poll_data["access_token"],
                        refresh_token=poll_data["refresh_token"],
                        expires_at=expires_at.isoformat(),
                    )

                    # Get user info
                    try:
                        user_response = await client.get(
                            "/auth/me",
                            headers={"Authorization": f"Bearer {poll_data['access_token']}"}
                        )
                        if user_response.status_code == 200:
                            user_data = user_response.json()
                            print(f"Logged in as {user_data.get('email', 'unknown')}\n")
                    except Exception:
                        print("Logged in successfully\n")

                    return True

            print("\nTimeout waiting for authorization.", file=sys.stderr)
            return False

    except Exception as e:
        print(f"\nLogin failed: {e}", file=sys.stderr)
        return False


def logout_flow() -> bool:
    """
    Logout by clearing stored credentials.

    Returns:
        True if credentials were cleared, False if no credentials existed
    """
    creds = credentials.get_credentials()
    if creds:
        credentials.clear_credentials()
        print("Logged out successfully.")
        return True
    else:
        print("No active session found.")
        return False


def main(args: list[str] | None = None) -> int:
    """
    Main CLI entry point.

    Args:
        args: Command-line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success, 1 for error)
    """
    if args is None:
        args = sys.argv[1:]

    # No args - show help
    if not args:
        print_help()
        return 0

    command = args[0].lower()

    if command in ("help", "-h", "--help"):
        print_help()
        return 0

    if command == "login":
        return handle_login(args[1:])

    if command == "logout":
        return handle_logout(args[1:])

    # Unknown command
    print(f"Unknown command: {command}", file=sys.stderr)
    print_help()
    return 1


def print_help() -> None:
    """Print CLI help message."""
    print("""
Bifrost CLI - Command-line interface for Bifrost SDK

Usage:
  bifrost <command> [options]

Commands:
  login       Authenticate with device authorization flow
  logout      Clear stored credentials and sign out
  help        Show this help message

Examples:
  bifrost login
  bifrost login --url https://app.gobifrost.com
  bifrost logout

For more information, visit: https://docs.gobifrost.com
""".strip())


def handle_login(args: list[str]) -> int:
    """
    Handle 'bifrost login' command.

    Args:
        args: Additional arguments (e.g., --url, --no-browser)

    Returns:
        Exit code (0 for success, 1 for error)
    """
    api_url = None
    auto_open = True

    # Parse arguments
    i = 0
    while i < len(args):
        arg = args[i]

        if arg in ("--url", "-u"):
            if i + 1 >= len(args):
                print("Error: --url requires a value", file=sys.stderr)
                return 1
            api_url = args[i + 1]
            i += 2
        elif arg in ("--no-browser", "-n"):
            auto_open = False
            i += 1
        elif arg in ("--help", "-h"):
            print("""
Usage: bifrost login [options]

Authenticate with Bifrost using device authorization flow.
Opens a browser window where you can enter the displayed code to authorize.

Options:
  --url, -u URL         API URL (default: BIFROST_DEV_URL or http://localhost:8000)
  --no-browser, -n      Don't automatically open browser
  --help, -h            Show this help message

Examples:
  bifrost login
  bifrost login --url https://app.gobifrost.com
  bifrost login --no-browser
""".strip())
            return 0
        else:
            print(f"Unknown option: {arg}", file=sys.stderr)
            return 1

    # Run login flow
    success = asyncio.run(login_flow(api_url=api_url, auto_open=auto_open))
    return 0 if success else 1


def handle_logout(args: list[str]) -> int:
    """
    Handle 'bifrost logout' command.

    Args:
        args: Additional arguments (e.g., --help)

    Returns:
        Exit code (0 for success, 1 for error)
    """
    if args and args[0] in ("--help", "-h"):
        print("""
Usage: bifrost logout

Clear stored credentials and sign out.
This removes the credentials file from your system.

Examples:
  bifrost logout
""".strip())
        return 0

    # Run logout
    logout_flow()
    return 0


if __name__ == "__main__":
    sys.exit(main())
