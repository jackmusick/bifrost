"""
Bifrost API - FastAPI Application

Main entry point for the FastAPI application.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from src.config import get_settings
from src.core.csrf import CSRFMiddleware
from src.core.database import close_db, init_db
from src.core.pubsub import manager as pubsub_manager
from src.core.workspace_sync import workspace_sync
from src.core.workspace_watcher import workspace_watcher
from src.routers import (
    auth_router,
    mfa_router,
    oauth_router,
    passkeys_router,
    health_router,
    organizations_router,
    users_router,
    roles_router,
    executions_router,
    workflows_router,
    forms_router,
    config_router,
    data_providers_router,
    websocket_router,
    branding_router,
    editor_files_router,
    schedules_router,
    workflow_keys_router,
    logs_router,
    metrics_router,
    packages_router,
    github_router,
    oauth_connections_router,
    endpoints_router,
    cli_router,
    notifications_router,
    profile_router,
    agents_router,
    chat_router,
    llm_config_router,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Suppress noisy third-party loggers
logging.getLogger("aiormq").setLevel(logging.WARNING)
logging.getLogger("aio_pika").setLevel(logging.WARNING)
logging.getLogger("watchdog").setLevel(logging.WARNING)
logging.getLogger("watchdog.observers.inotify_buffer").setLevel(logging.WARNING)

# Enable DEBUG for execution engine to troubleshoot workflows
logging.getLogger("src.services.execution").setLevel(logging.DEBUG)
logging.getLogger("bifrost").setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting Bifrost API...")
    settings = get_settings()

    # Initialize database
    logger.info("Initializing database connection...")
    await init_db()
    logger.info("Database connection established")

    # Start workspace sync service (downloads from S3, listens for pub/sub changes)
    logger.info("Starting workspace sync service...")
    await workspace_sync.start()
    logger.info("Workspace sync service started")

    # Start workspace watcher (detects local changes, publishes to others)
    logger.info("Starting workspace watcher...")
    await workspace_watcher.start()
    logger.info("Workspace watcher started")

    # Register dynamic workflow endpoints for OpenAPI documentation
    logger.info("Registering workflow endpoints...")
    await register_dynamic_workflow_endpoints(app)

    # Create default admin user if configured via environment variables
    if settings.default_user_email and settings.default_user_password:
        await create_default_user()

    logger.info(f"Bifrost API started in {settings.environment} mode")

    yield

    # Shutdown
    logger.info("Shutting down Bifrost API...")

    await workspace_watcher.stop()
    await workspace_sync.stop()
    await pubsub_manager.close()
    await close_db()
    logger.info("Bifrost API shutdown complete")


async def register_dynamic_workflow_endpoints(app: FastAPI) -> None:
    """
    Register dynamic routes for endpoint-enabled workflows.

    This creates per-workflow OpenAPI documentation with proper parameter
    schemas for each workflow that has endpoint_enabled=True.
    """
    from src.core.database import get_db_context
    from src.services.openapi_endpoints import register_workflow_endpoints

    try:
        async with get_db_context() as db:
            count = await register_workflow_endpoints(app, db)
            logger.info(f"Registered {count} dynamic workflow endpoints")
    except Exception as e:
        # Don't fail startup if endpoint registration fails
        logger.warning(f"Failed to register workflow endpoints: {e}")


async def create_default_user() -> None:
    """
    Create default admin user if it doesn't exist.

    Only runs if BIFROST_DEFAULT_USER_EMAIL and BIFROST_DEFAULT_USER_PASSWORD
    environment variables are set. This is useful for automated deployments
    where you want to pre-configure an admin account.

    If not configured, users will go through the setup wizard on first access.
    """
    from src.core.database import get_db_context
    from src.core.security import get_password_hash
    from src.repositories.users import UserRepository

    settings = get_settings()

    if not settings.default_user_email or not settings.default_user_password:
        return

    async with get_db_context() as db:
        user_repo = UserRepository(db)

        # Check if default user exists
        existing = await user_repo.get_by_email(settings.default_user_email)
        if existing:
            logger.info(f"Default user already exists: {settings.default_user_email}")
            return

        # Create default admin user
        hashed_password = get_password_hash(settings.default_user_password)
        user = await user_repo.create_user(
            email=settings.default_user_email,
            hashed_password=hashed_password,
            name="Admin",
            is_superuser=True,
        )
        logger.info(f"Created default admin user: {user.email} (id: {user.id})")


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title="Bifrost API",
        description="MSP automation platform API",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Note: CORS middleware not needed - frontend proxies all /api requests
    # through Vite dev server (dev) or nginx (prod), making them same-origin.

    # Add CSRF protection middleware
    # Only enforces for cookie-based auth with unsafe methods (POST, PUT, DELETE, PATCH)
    # Bearer token auth is exempt since browsers don't automatically include it
    app.add_middleware(CSRFMiddleware)

    # Register routers
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(mfa_router)
    app.include_router(oauth_router)
    app.include_router(passkeys_router)
    app.include_router(organizations_router)
    app.include_router(users_router)
    app.include_router(roles_router)
    app.include_router(executions_router)
    app.include_router(workflows_router)
    app.include_router(forms_router)
    app.include_router(config_router)
    app.include_router(data_providers_router)
    app.include_router(websocket_router)
    app.include_router(branding_router)
    app.include_router(editor_files_router)
    app.include_router(schedules_router)
    app.include_router(workflow_keys_router)
    app.include_router(logs_router)
    app.include_router(metrics_router)
    app.include_router(packages_router)
    app.include_router(github_router)
    app.include_router(oauth_connections_router)
    app.include_router(endpoints_router)
    app.include_router(cli_router)
    app.include_router(notifications_router)
    app.include_router(profile_router)
    app.include_router(agents_router)
    app.include_router(chat_router)
    app.include_router(llm_config_router)

    # Root endpoint
    @app.get("/")
    async def root():
        return {
            "name": "Bifrost API",
            "version": "2.0.0",
            "docs": "/docs",
        }

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
    )
