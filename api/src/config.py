"""
Application Configuration

Uses pydantic-settings for environment variable loading with validation.
All configuration is centralized here for easy management.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Environment variables can be set directly or via .env file.
    All secrets should be provided via environment variables in production.
    """

    model_config = SettingsConfigDict(
        env_prefix="BIFROST_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ==========================================================================
    # Environment
    # ==========================================================================
    environment: Literal["development", "testing", "production"] = Field(
        default="development",
        description="Runtime environment"
    )

    debug: bool = Field(
        default=False,
        description="Enable debug mode"
    )

    # ==========================================================================
    # Database (PostgreSQL)
    # ==========================================================================
    database_url: str = Field(
        default="postgresql+asyncpg://bifrost:bifrost_dev@localhost:5432/bifrost",
        description="Async PostgreSQL connection URL"
    )

    database_url_sync: str = Field(
        default="postgresql://bifrost:bifrost_dev@localhost:5432/bifrost",
        description="Sync PostgreSQL connection URL (for Alembic)"
    )

    database_pool_size: int = Field(
        default=5,
        description="Database connection pool size"
    )

    database_max_overflow: int = Field(
        default=10,
        description="Max overflow connections beyond pool size"
    )

    # ==========================================================================
    # RabbitMQ
    # ==========================================================================
    rabbitmq_url: str = Field(
        default="amqp://bifrost:bifrost_dev@localhost:5672/",
        description="RabbitMQ connection URL"
    )

    # ==========================================================================
    # Workflow Execution
    # ==========================================================================
    max_concurrency: int = Field(
        default=10,
        description="Max concurrent workflow executions (controls both RabbitMQ prefetch and subprocess pool)"
    )
    execution_timeout_seconds: int = Field(
        default=300,
        description="Default execution timeout in seconds (5 minutes)"
    )
    graceful_shutdown_seconds: int = Field(
        default=3,
        description="Seconds to wait after SIGTERM before SIGKILL"
    )
    cancel_check_interval_ms: int = Field(
        default=250,
        description="How often to check for cancellation (milliseconds)"
    )
    memory_throttle_threshold_mb: int = Field(
        default=300,
        description="Minimum available memory (MB) required to start new subprocess"
    )

    # ==========================================================================
    # Redis
    # ==========================================================================
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )

    # ==========================================================================
    # Security
    # ==========================================================================
    secret_key: str = Field(
        default="dev-secret-key-change-in-production-must-be-32-chars",
        description="Secret key for JWT signing and encryption",
        min_length=32
    )

    algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm"
    )

    access_token_expire_minutes: int = Field(
        default=30,
        description="Access token expiration time in minutes"
    )

    refresh_token_expire_days: int = Field(
        default=7,
        description="Refresh token expiration time in days"
    )

    jwt_issuer: str = Field(
        default="bifrost-api",
        description="JWT issuer claim for token validation"
    )

    jwt_audience: str = Field(
        default="bifrost-client",
        description="JWT audience claim for token validation"
    )

    fernet_salt: str = Field(
        default="bifrost_secrets_v1",
        description="Salt for Fernet key derivation (override for different encryption keys)"
    )

    oauth_require_mfa: bool = Field(
        default=False,
        description="If True, require MFA even for OAuth users"
    )

    # ==========================================================================
    # CORS
    # ==========================================================================
    cors_origins: str = Field(
        default="http://localhost:3000",
        description="Comma-separated list of allowed CORS origins"
    )

    @computed_field
    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # ==========================================================================
    # S3 Storage (for horizontal scaling)
    # ==========================================================================
    instance_id: str = Field(
        default="local",
        description="Instance ID for unique bucket names (e.g., 'local', 'prod', or a UUID)"
    )

    s3_endpoint_url: str | None = Field(
        default=None,
        description="S3 endpoint URL (None for AWS, 'http://minio:9000' for local MinIO)"
    )

    s3_access_key: str | None = Field(
        default=None,
        description="S3 access key"
    )

    s3_secret_key: str | None = Field(
        default=None,
        description="S3 secret key"
    )

    s3_region: str = Field(
        default="us-east-1",
        description="S3 region"
    )

    @computed_field
    @property
    def s3_workspace_bucket(self) -> str:
        """Bucket name for workspace files (indexed, git-tracked)."""
        return f"bifrost-{self.instance_id}-workspace"

    @computed_field
    @property
    def s3_files_bucket(self) -> str:
        """Bucket name for runtime files (blob storage, not indexed)."""
        return f"bifrost-{self.instance_id}-files"

    @computed_field
    @property
    def s3_configured(self) -> bool:
        """Check if S3 storage is configured."""
        return bool(self.s3_access_key and self.s3_secret_key)

    # ==========================================================================
    # File Storage (Legacy - used when S3 not configured)
    # ==========================================================================
    workspace_location: str | None = Field(
        default=None,
        description="Path to workspace directory (legacy, used when S3 not configured)"
    )

    temp_location: str = Field(
        default="/tmp/bifrost",
        description="Path to temporary storage directory"
    )

    # ==========================================================================
    # Default User (for automated deployments and development)
    # ==========================================================================
    default_user_email: str | None = Field(
        default=None,
        description="Default admin user email (creates user on startup if set)"
    )

    default_user_password: str | None = Field(
        default=None,
        description="Default admin user password"
    )

    # ==========================================================================
    # MFA Settings
    # ==========================================================================
    mfa_enabled: bool = Field(
        default=True,
        description="Whether MFA is required for password authentication"
    )

    mfa_totp_issuer: str = Field(
        default="Bifrost",
        description="Issuer name for TOTP QR codes"
    )

    mfa_recovery_code_count: int = Field(
        default=10,
        description="Number of recovery codes to generate for MFA"
    )

    mfa_trusted_device_days: int = Field(
        default=30,
        description="Number of days a device stays trusted after MFA verification"
    )

    # ==========================================================================
    # OAuth SSO (Single Sign-On)
    # ==========================================================================
    # Microsoft Entra ID (Azure AD)
    microsoft_client_id: str | None = Field(
        default=None,
        description="Microsoft OAuth client ID"
    )
    microsoft_client_secret: str | None = Field(
        default=None,
        description="Microsoft OAuth client secret"
    )
    microsoft_tenant_id: str | None = Field(
        default=None,
        description="Microsoft tenant ID (or 'common' for multi-tenant)"
    )

    # Google OAuth
    google_client_id: str | None = Field(
        default=None,
        description="Google OAuth client ID"
    )
    google_client_secret: str | None = Field(
        default=None,
        description="Google OAuth client secret"
    )

    # Generic OIDC Provider
    oidc_discovery_url: str | None = Field(
        default=None,
        description="OIDC discovery URL (e.g., https://provider/.well-known/openid-configuration)"
    )
    oidc_client_id: str | None = Field(
        default=None,
        description="OIDC client ID"
    )
    oidc_client_secret: str | None = Field(
        default=None,
        description="OIDC client secret"
    )

    # Frontend URL (for OAuth redirects)
    frontend_url: str = Field(
        default="http://localhost:3000",
        description="Frontend URL for OAuth callback redirects"
    )

    # ==========================================================================
    # Server
    # ==========================================================================
    host: str = Field(
        default="0.0.0.0",
        description="Server host"
    )

    port: int = Field(
        default=8000,
        description="Server port"
    )

    # ==========================================================================
    # Computed Properties
    # ==========================================================================
    @computed_field
    @property
    def microsoft_oauth_configured(self) -> bool:
        """Check if Microsoft OAuth is configured."""
        return bool(self.microsoft_client_id and self.microsoft_client_secret)

    @computed_field
    @property
    def google_oauth_configured(self) -> bool:
        """Check if Google OAuth is configured."""
        return bool(self.google_client_id and self.google_client_secret)

    @computed_field
    @property
    def oidc_configured(self) -> bool:
        """Check if generic OIDC is configured."""
        return bool(self.oidc_discovery_url and self.oidc_client_id and self.oidc_client_secret)

    @computed_field
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"

    @computed_field
    @property
    def is_testing(self) -> bool:
        """Check if running in testing mode."""
        return self.environment == "testing"

    @computed_field
    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"

    def validate_paths(self) -> None:
        """
        Validate that required filesystem paths exist.

        With S3 storage, workspace_location is optional.
        Without S3, workspace_location must be set and exist.

        Raises:
            ValueError: If workspace location required but doesn't exist
        """
        # If S3 is configured, workspace_location is not required
        if not self.s3_configured:
            if not self.workspace_location:
                raise ValueError(
                    "Either S3 storage (BIFROST_S3_ACCESS_KEY, BIFROST_S3_SECRET_KEY) "
                    "or BIFROST_WORKSPACE_LOCATION must be configured."
                )
            workspace = Path(self.workspace_location)
            if not workspace.exists():
                raise ValueError(
                    f"Workspace location does not exist: {self.workspace_location}. "
                    "Please create it or configure S3 storage instead."
                )

        # Create temp location if it doesn't exist
        temp = Path(self.temp_location)
        temp.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()
