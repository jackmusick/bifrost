"""
Shared Services for Bifrost Integrations

This package contains business logic services that operate on data models
and provide functionality to the HTTP endpoints and other consumers.

Services:
- oauth_storage_service: OAuth connection management
- oauth_provider: OAuth provider client for authorization flows
- workspace_service: Workspace and file management (legacy filesystem)
- file_storage_service: S3-based file storage with indexing
- blob_storage_service: S3-based blob storage for runtime files
- temp_file_service: Temporary file handling
- zip_service: ZIP file creation and management
"""

# Re-export commonly used services
from shared.services.oauth_storage_service import OAuthStorageService
from shared.services.oauth_provider import OAuthProviderClient
from shared.services.workspace_service import WorkspaceService, get_workspace_service
from shared.services.file_storage_service import FileStorageService, get_file_storage_service
from shared.services.blob_storage_service import BlobStorageService, get_blob_storage_service
from shared.services.temp_file_service import (
    TempFileService,
    get_temp_file_service,
)
from shared.services.zip_service import (
    create_workspace_zip,
    create_selective_zip,
    estimate_workspace_size,
)

__all__ = [
    # OAuth services
    "OAuthStorageService",
    "OAuthProviderClient",

    # File services (legacy filesystem)
    "WorkspaceService",
    "get_workspace_service",

    # Storage services (S3-based)
    "FileStorageService",
    "get_file_storage_service",
    "BlobStorageService",
    "get_blob_storage_service",

    # Utility services
    "TempFileService",
    "get_temp_file_service",
    "create_workspace_zip",
    "create_selective_zip",
    "estimate_workspace_size",
]
