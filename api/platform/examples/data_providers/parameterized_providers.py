"""
Example Data Providers with Parameters (T041)
Demonstrates parameter usage with data providers using function signature type hints
"""

from bifrost import data_provider


@data_provider(
    name="get_github_repos",
    description="Get GitHub repositories for an organization (requires GitHub token)",
)
async def get_github_repos(token: str, org: str = ""):
    """
    Example data provider that requires a GitHub token parameter.

    This is a mock implementation for testing purposes.
    In production, this would make real GitHub API calls.

    Args:
        token: GitHub personal access token
        org: Optional GitHub organization name

    Returns:
        List of repository options with label/value format
    """
    # Mock implementation for testing
    # In production, you would use the token to call GitHub API:
    # headers = {"Authorization": f"Bearer {token}"}
    # response = requests.get(f"https://api.github.com/orgs/{org}/repos", headers=headers)

    # Return mock data based on inputs
    if org:
        return [
            {
                "label": f"{org}/repo-1",
                "value": f"{org}/repo-1",
                "metadata": {"stars": 42, "private": False}
            },
            {
                "label": f"{org}/repo-2",
                "value": f"{org}/repo-2",
                "metadata": {"stars": 15, "private": True}
            },
        ]
    else:
        return [
            {
                "label": "my-personal-repo",
                "value": "user/my-personal-repo",
                "metadata": {"stars": 5, "private": False}
            }
        ]


@data_provider(
    name="get_github_branches",
    description="Get branches for a GitHub repository",
)
async def get_github_branches(token: str, repo: str):
    """
    Example data provider for getting repository branches.

    Args:
        token: GitHub personal access token
        repo: Repository in format "owner/name"

    Returns:
        List of branch options
    """
    # Mock implementation
    return [
        {"label": "main", "value": "main", "metadata": {"protected": True}},
        {"label": "develop", "value": "develop", "metadata": {"protected": False}},
        {"label": "feature/new-ui", "value": "feature/new-ui",
            "metadata": {"protected": False}},
    ]


@data_provider(
    name="get_filtered_licenses",
    description="Get Microsoft 365 licenses with filtering",
)
async def get_filtered_licenses(filter: str = "all"):
    """
    Example data provider with optional parameter and default value.

    Args:
        filter: Filter mode ('all', 'available', 'assigned')

    Returns:
        List of license options based on filter
    """
    all_licenses = [
        {"label": "Microsoft 365 E3", "value": "SPE_E3",
            "metadata": {"available": 10, "assigned": 5}},
        {"label": "Microsoft 365 E5", "value": "SPE_E5",
            "metadata": {"available": 0, "assigned": 3}},
        {"label": "Office 365 E1", "value": "O365_E1",
            "metadata": {"available": 20, "assigned": 0}},
    ]

    if filter == "available":
        return [lic for lic in all_licenses if lic["metadata"]["available"] > 0]
    elif filter == "assigned":
        return [lic for lic in all_licenses if lic["metadata"]["assigned"] > 0]
    else:
        return all_licenses
