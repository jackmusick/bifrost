"""
Common contract models for Bifrost (errors, branding, uploads, packages).
"""

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    pass


# ==================== ERROR MODELS ====================


class ErrorResponse(BaseModel):
    """API error response"""
    error: str = Field(..., description="Error code or type")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = None


# ==================== BRANDING MODELS ====================


class BrandingSettings(BaseModel):
    """Global platform branding configuration"""
    square_logo_url: str | None = Field(None, description="Square logo URL (for icons, 1:1 ratio)")
    rectangle_logo_url: str | None = Field(None, description="Rectangle logo URL (for headers, 16:9 ratio)")
    primary_color: str | None = Field(None, description="Primary brand color (hex format, e.g., #FF5733)")

    @field_validator('primary_color')
    @classmethod
    def validate_hex_color(cls, v):
        """Validate hex color format"""
        if v is None:
            return v
        if not v.startswith('#') or len(v) not in [4, 7]:
            raise ValueError("Primary color must be a valid hex color (e.g., #FFF or #FF5733)")
        try:
            int(v[1:], 16)
        except ValueError:
            raise ValueError("Primary color must be a valid hex color")
        return v


class BrandingUpdateRequest(BaseModel):
    """Request model for updating primary color only - logos use POST /logo/{type}"""
    primary_color: str | None = Field(None, description="Primary color (hex code, e.g., #0066CC)")


# ==================== FILE UPLOAD MODELS ====================


class FileUploadRequest(BaseModel):
    """Request model for generating file upload SAS URL"""
    file_name: str = Field(..., description="Original file name")
    content_type: str = Field(..., description="MIME type of the file")
    file_size: int = Field(..., description="File size in bytes")


class UploadedFileMetadata(BaseModel):
    """Metadata for uploaded file that workflows can use to access the file"""
    name: str = Field(..., description="Original file name")
    container: str = Field(..., description="Blob storage container name (e.g., 'uploads')")
    path: str = Field(..., description="Blob path within container")
    content_type: str = Field(..., description="MIME type of the file")
    size: int = Field(..., description="File size in bytes")


class FileUploadResponse(BaseModel):
    """Response model for file upload SAS URL generation"""
    upload_url: str = Field(..., description="URL for direct upload")
    blob_uri: str = Field(..., description="Final file URI")
    expires_at: str = Field(..., description="Token expiration timestamp (ISO format)")
    file_metadata: UploadedFileMetadata = Field(..., description="Metadata for accessing the uploaded file in workflows")


# ==================== PACKAGE MANAGEMENT MODELS ====================


class InstallPackageRequest(BaseModel):
    """Request model for installing a package"""
    package_name: str = Field(..., min_length=1, description="Package name (e.g., 'requests')")
    version: str | None = Field(None, description="Version specifier (e.g., '>=2.28.0')")


class PackageInstallResponse(BaseModel):
    """Response model for package installation"""
    package_name: str
    version: str | None = None
    status: str = Field(..., description="Installation status (success, failed, in_progress)")
    message: str = Field(..., description="Installation message")


class InstalledPackage(BaseModel):
    """Installed package information"""
    name: str
    version: str


class InstalledPackagesResponse(BaseModel):
    """Response model for listing installed packages"""
    packages: list[InstalledPackage]
    total_count: int


class PackageUpdate(BaseModel):
    """Package update information"""
    name: str
    current_version: str
    latest_version: str


class PackageUpdatesResponse(BaseModel):
    """Response model for package update check"""
    updates_available: list[PackageUpdate]
    total_count: int
