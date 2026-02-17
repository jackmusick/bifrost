"""Public embed entry point — HMAC-verified iframe loading."""

import logging

from fastapi import APIRouter, HTTPException, Path, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.responses import RedirectResponse

from src.core.database import get_db_context
from src.core.security import create_embed_token, decrypt_secret
from src.models.orm.applications import Application
from src.services.embed_auth import verify_embed_hmac

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/embed",
    tags=["Embed"],
)


@router.get("/apps/{slug}")
async def embed_app(
    request: Request,
    slug: str = Path(...),
):
    """Public entry point for HMAC-authenticated iframe embedding.

    Verifies the HMAC signature against the app's embed secrets,
    issues an 8-hour embed JWT cookie, and returns a confirmation response.
    """
    query_params = dict(request.query_params)

    if "hmac" not in query_params:
        raise HTTPException(status_code=403, detail="Missing HMAC signature")

    # Look up the app and its active embed secrets (no auth required — public endpoint)
    async with get_db_context() as db:
        result = await db.execute(
            select(Application)
            .where(Application.slug == slug)
            .options(selectinload(Application.embed_secrets))
        )
        app = result.scalar_one_or_none()

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    active_secrets = [s for s in app.embed_secrets if s.is_active]
    if not active_secrets:
        raise HTTPException(status_code=403, detail="No embed secrets configured")

    # Try each active secret
    verified = False
    for secret_record in active_secrets:
        raw_secret = decrypt_secret(secret_record.secret_encrypted)
        if verify_embed_hmac(query_params, raw_secret):
            verified = True
            break

    if not verified:
        raise HTTPException(status_code=403, detail="Invalid HMAC signature")

    # Extract verified params (everything except hmac)
    verified_params = {k: v for k, v in query_params.items() if k != "hmac"}

    # Issue embed JWT
    embed_token = create_embed_token(
        app_id=str(app.id),
        org_id=str(app.organization_id) if app.organization_id else None,
        verified_params=verified_params,
    )

    # Build redirect response
    redirect = RedirectResponse(
        url=f"/apps/{app.slug}",
        status_code=302,
    )

    # Set cookie on the redirect response
    redirect.set_cookie(
        key="embed_token",
        value=embed_token,
        httponly=True,
        samesite="none",
        secure=True,
        max_age=8 * 3600,
        path="/",
    )

    # Set permissive framing headers for embed route
    redirect.headers["Content-Security-Policy"] = "frame-ancestors *"
    redirect.headers["X-Frame-Options"] = "ALLOWALL"

    return redirect
