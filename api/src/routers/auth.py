"""
Authentication Router

Provides endpoints for user authentication:
- Login (JWT token generation with user provisioning)
- Token refresh with rotation
- Token revocation (logout, revoke-all)
- Current user info

Key Features:
- First user login auto-promotes to PlatformAdmin
- Subsequent users auto-join organizations by email domain
- JWT tokens include user_type, org_id, and roles
- Refresh tokens use JTI for revocation support
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr

from src.core.cache import get_shared_redis
from src.core.cache.keys import (
    refresh_token_jti_key,
    user_refresh_tokens_pattern,
    TTL_REFRESH_TOKEN,
)
from src.models.models import OAuthProviderInfo, AuthStatusResponse
from src.config import get_settings
from src.core.auth import CurrentActiveUser
from src.core.database import DbSession
from src.core.rate_limit import auth_limiter, mfa_limiter, get_client_ip
from src.core.security import (
    create_access_token,
    create_mfa_token,
    create_refresh_token,
    decode_mfa_token,
    decode_token,
    generate_csrf_token,
    get_password_hash,
    verify_password,
)
from src.repositories.users import UserRepository
from src.services.user_provisioning import ensure_user_provisioned, get_user_roles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# =============================================================================
# Cookie Configuration
# =============================================================================

def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    """
    Set HttpOnly authentication cookies and CSRF token.

    Cookies are secure, SameSite=Lax, and HttpOnly for XSS protection.
    This provides automatic auth for browser clients while still allowing
    service-to-service auth via Authorization header.

    Also sets a CSRF token cookie that JavaScript can read and send as a header.
    """
    settings = get_settings()

    # Determine if we're in production (HTTPS)
    secure = not settings.is_development

    # Access token cookie (short-lived)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=30 * 60,  # 30 minutes (matches JWT expiry)
        path="/",
    )

    # Refresh token cookie (long-lived)
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,  # 7 days (matches JWT expiry)
        path="/",
    )

    # CSRF token cookie (readable by JavaScript for X-CSRF-Token header)
    csrf_token = generate_csrf_token()
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,  # JS needs to read this
        secure=secure,
        samesite="strict",  # Stricter for CSRF protection
        max_age=30 * 60,  # Match access token expiry
        path="/",
    )


def clear_auth_cookies(response: Response):
    """Clear authentication cookies on logout."""
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")
    response.delete_cookie(key="csrf_token", path="/")


# =============================================================================
# Refresh Token JTI Management
# =============================================================================


async def store_refresh_token_jti(user_id: str, jti: str) -> None:
    """
    Store a refresh token JTI in Redis for validation/revocation.

    Args:
        user_id: User ID the token belongs to
        jti: JWT ID to store
    """
    r = await get_shared_redis()
    key = refresh_token_jti_key(user_id, jti)
    await r.setex(key, TTL_REFRESH_TOKEN, "1")


async def validate_and_revoke_refresh_token_jti(user_id: str, jti: str) -> bool:
    """
    Validate a refresh token JTI exists and revoke it (single use).

    Args:
        user_id: User ID the token belongs to
        jti: JWT ID to validate

    Returns:
        True if JTI was valid and has been revoked, False if invalid
    """
    r = await get_shared_redis()
    key = refresh_token_jti_key(user_id, jti)

    # Atomically check and delete
    result = await r.delete(key)
    return result > 0


async def revoke_all_user_refresh_tokens(user_id: str) -> int:
    """
    Revoke all refresh tokens for a user.

    Args:
        user_id: User ID to revoke tokens for

    Returns:
        Number of tokens revoked
    """
    r = await get_shared_redis()
    pattern = user_refresh_tokens_pattern(user_id)

    # Find all keys matching pattern
    keys = []
    async for key in r.scan_iter(match=pattern):
        keys.append(key)

    if keys:
        return await r.delete(*keys)
    return 0


# =============================================================================
# Request/Response Models
# =============================================================================

class Token(BaseModel):
    """Token response model."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MFARequiredResponse(BaseModel):
    """Response when MFA verification is required."""
    mfa_required: bool = True
    mfa_token: str
    available_methods: list[str]
    expires_in: int = 300  # 5 minutes


class MFASetupRequiredResponse(BaseModel):
    """Response when MFA enrollment is required."""
    mfa_setup_required: bool = True
    mfa_token: str
    expires_in: int = 300  # 5 minutes


class MFAVerifyRequest(BaseModel):
    """Request to verify MFA code during login."""
    mfa_token: str
    code: str
    trust_device: bool = False
    device_name: str | None = None


class LoginResponse(BaseModel):
    """Unified login response that can be Token or MFA response."""
    # Token fields (when MFA not required or after MFA verification)
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    # MFA fields (when MFA required)
    mfa_required: bool = False
    mfa_setup_required: bool = False
    mfa_token: str | None = None
    available_methods: list[str] | None = None
    expires_in: int | None = None


class TokenRefresh(BaseModel):
    """Token refresh request model."""
    refresh_token: str


class UserResponse(BaseModel):
    """User response model."""
    id: str
    email: str
    name: str
    is_active: bool
    is_superuser: bool
    is_verified: bool
    user_type: str
    organization_id: str | None
    roles: list[str] = []


class UserCreate(BaseModel):
    """User creation request model."""
    email: EmailStr
    password: str
    name: str | None = None


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/login", response_model=LoginResponse)
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None,
    db: DbSession = None,
) -> LoginResponse:
    """
    Login with email and password.

    For email/password authentication, MFA is REQUIRED:
    - If user has MFA enrolled: returns mfa_required=True with mfa_token
    - If user has no MFA: returns mfa_setup_required=True to redirect to enrollment

    Performs user provisioning on each login:
    - First user in system becomes PlatformAdmin
    - Subsequent users are matched to organizations by email domain
    - JWT tokens include user_type, org_id, and roles for authorization

    Rate limited: 10 requests per minute per IP address.

    Args:
        form_data: OAuth2 password form with username (email) and password
        request: FastAPI request object
        db: Database session

    Returns:
        LoginResponse with either tokens (MFA bypass for trusted device) or MFA requirements

    Raises:
        HTTPException: If credentials are invalid or provisioning fails
    """
    from src.services.mfa_service import MFAService

    # Rate limiting
    client_ip = get_client_ip(request)
    await auth_limiter.check("login", client_ip)

    user_repo = UserRepository(db)
    user = await user_repo.get_by_email(form_data.username)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account does not have password authentication enabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    # Check MFA status - MFA is REQUIRED for password login
    mfa_service = MFAService(db)
    mfa_status = await mfa_service.get_mfa_status(user)

    if not user.mfa_enabled or not mfa_status["enrolled_methods"]:
        # User has no MFA enrolled - require setup
        mfa_token = create_mfa_token(str(user.id), purpose="mfa_setup")

        logger.info(
            f"MFA setup required for user: {user.email}",
            extra={"user_id": str(user.id)}
        )

        return LoginResponse(
            mfa_setup_required=True,
            mfa_token=mfa_token,
            expires_in=300,
        )

    # User has MFA - check for trusted device
    if request:
        user_agent = request.headers.get("user-agent", "")
        fingerprint = MFAService.generate_device_fingerprint(user_agent)
        client_ip = request.client.host if request.client else None

        if await mfa_service.is_device_trusted(user.id, fingerprint, client_ip):
            # Trusted device - skip MFA verification
            logger.info(
                f"Trusted device login for user: {user.email}",
                extra={"user_id": str(user.id)}
            )
            return await _generate_login_tokens(user, db, response)

    # MFA verification required
    mfa_token = create_mfa_token(str(user.id), purpose="mfa_verify")

    logger.info(
        f"MFA verification required for user: {user.email}",
        extra={"user_id": str(user.id)}
    )

    return LoginResponse(
        mfa_required=True,
        mfa_token=mfa_token,
        available_methods=mfa_status["enrolled_methods"],
        expires_in=300,
    )


class MFASetupTokenRequest(BaseModel):
    """Request with MFA token for initial setup."""
    mfa_token: str


class MFASetupResponse(BaseModel):
    """MFA setup response with secret."""
    secret: str
    qr_code_uri: str
    provisioning_uri: str
    issuer: str
    account_name: str


class MFAEnrollVerifyRequest(BaseModel):
    """Request to verify MFA during initial enrollment."""
    mfa_token: str
    code: str


class MFAEnrollVerifyResponse(BaseModel):
    """Response after completing MFA enrollment."""
    success: bool
    recovery_codes: list[str]
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@router.post("/mfa/setup", response_model=MFASetupResponse)
async def mfa_initial_setup(
    db: DbSession = None,
    request: Request = None,
) -> MFASetupResponse:
    """
    Initialize MFA enrollment during first-time setup.

    This endpoint is for users who just logged in with password for the first time
    and need to enroll in MFA. Requires an mfa_token with purpose "mfa_setup"
    in the Authorization header.

    Returns:
        MFA setup data including secret and QR code URI

    Raises:
        HTTPException: If MFA token is invalid or expired
    """
    from src.services.mfa_service import MFAService

    # Get mfa_token from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    mfa_token = auth_header.replace("Bearer ", "")

    # Validate MFA token with purpose "mfa_setup"
    payload = decode_mfa_token(mfa_token, "mfa_setup")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired MFA setup token",
        )

    user_id = UUID(payload["sub"])

    # Get user from database
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    mfa_service = MFAService(db)
    setup_data = await mfa_service.setup_totp(user)
    await db.commit()

    logger.info(
        f"MFA setup initiated for user: {user.email}",
        extra={"user_id": str(user.id)}
    )

    return MFASetupResponse(**setup_data)


@router.post("/mfa/verify", response_model=MFAEnrollVerifyResponse)
async def mfa_initial_verify(
    response: Response,
    db: DbSession = None,
    request: Request = None,
) -> MFAEnrollVerifyResponse:
    """
    Verify MFA code to complete initial enrollment.

    This endpoint is for users completing their first MFA setup after password login.
    Requires an mfa_token with purpose "mfa_setup" in the Authorization header.

    On success:
    - Activates the MFA method
    - Generates recovery codes (shown only once!)
    - Returns access tokens for auto-login

    Returns:
        Success status, recovery codes, and access tokens

    Raises:
        HTTPException: If MFA token is invalid or code verification fails
    """
    from src.services.mfa_service import MFAService

    logger.info("MFA initial verify endpoint called")

    # Get mfa_token from Authorization header
    auth_header = request.headers.get("Authorization", "")
    logger.info(f"Auth header present: {bool(auth_header)}, starts with Bearer: {auth_header.startswith('Bearer ')}")

    if not auth_header.startswith("Bearer "):
        logger.warning("Missing or invalid Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    mfa_token = auth_header.replace("Bearer ", "")
    logger.info(f"MFA token length: {len(mfa_token)}")

    # Validate MFA token with purpose "mfa_setup"
    payload = decode_mfa_token(mfa_token, "mfa_setup")
    logger.info(f"MFA token decode result: {payload is not None}")
    if not payload:
        logger.warning("Invalid or expired MFA setup token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired MFA setup token",
        )

    user_id = UUID(payload["sub"])

    # Get code from request body
    body = await request.json()
    code = body.get("code", "")

    if not code or len(code) != 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA code format",
        )

    # Get user from database
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    mfa_service = MFAService(db)

    try:
        recovery_codes = await mfa_service.verify_totp_enrollment(user, code)
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    logger.info(
        f"MFA enrollment completed for user: {user.email}",
        extra={"user_id": str(user.id)}
    )

    # Generate tokens for auto-login after MFA enrollment
    db_roles = await get_user_roles(db, user.id)
    roles = ["authenticated"]
    if user.is_superuser:
        roles.append("PlatformAdmin")
    else:
        roles.append("OrgUser")
    roles.extend(db_roles)

    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name or user.email.split("@")[0],
        "user_type": user.user_type.value,
        "is_superuser": user.is_superuser,
        "org_id": str(user.organization_id) if user.organization_id else None,
        "roles": roles,
    }

    access_token = create_access_token(data=token_data)
    refresh_token_str, jti = create_refresh_token(data={"sub": str(user.id)})

    # Store JTI in Redis for revocation support
    await store_refresh_token_jti(str(user.id), jti)

    # Set cookies for browser clients
    set_auth_cookies(response, access_token, refresh_token_str)

    return MFAEnrollVerifyResponse(
        success=True,
        recovery_codes=recovery_codes,
        access_token=access_token,
        refresh_token=refresh_token_str,
    )


@router.post("/mfa/login", response_model=LoginResponse)
async def verify_mfa_login(
    response: Response,
    mfa_request: MFAVerifyRequest,
    request: Request = None,
    db: DbSession = None,
) -> LoginResponse:
    """
    Complete MFA verification during login to get access tokens.

    This is used when an existing user with MFA logs in and needs to verify their code.
    For initial MFA enrollment verification, use POST /auth/mfa/verify.

    Rate limited: 5 requests per minute per IP address.

    Args:
        mfa_request: MFA verification request with token, code, and trust options
        request: FastAPI request object
        db: Database session

    Returns:
        LoginResponse with access and refresh tokens

    Raises:
        HTTPException: If MFA token is invalid or code verification fails
    """
    from src.services.mfa_service import MFAService

    # Rate limiting (stricter for MFA to prevent brute force)
    client_ip = get_client_ip(request)
    await mfa_limiter.check("mfa_verify", client_ip)

    # Validate MFA token
    payload = decode_mfa_token(mfa_request.mfa_token, "mfa_verify")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired MFA token",
        )

    user_id = UUID(payload["sub"])

    # Get user from database
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    mfa_service = MFAService(db)

    # Check if code is a recovery code (longer format)
    code = mfa_request.code.replace("-", "").upper()
    is_recovery = len(code) == 8 and not code.isdigit()

    if is_recovery:
        # Verify recovery code
        client_ip = request.client.host if request and request.client else None
        if not await mfa_service.verify_recovery_code(user.id, mfa_request.code, client_ip):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid recovery code",
            )
    else:
        # Verify TOTP code
        if not await mfa_service.verify_totp_code(user.id, mfa_request.code):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA code",
            )

    # Optionally trust this device
    if mfa_request.trust_device and request:
        user_agent = request.headers.get("user-agent", "")
        fingerprint = MFAService.generate_device_fingerprint(user_agent)
        client_ip = request.client.host if request.client else None

        await mfa_service.create_trusted_device(
            user_id=user.id,
            fingerprint=fingerprint,
            device_name=mfa_request.device_name,
            ip_address=client_ip,
        )

    await db.commit()

    logger.info(
        f"MFA verification successful for user: {user.email}",
        extra={"user_id": str(user.id)}
    )

    return await _generate_login_tokens(user, db, response)


async def _generate_login_tokens(user, db, response: Response | None = None) -> LoginResponse:
    """
    Generate login response with access and refresh tokens.

    Sets HttpOnly cookies for browser clients when response is provided.
    Also returns tokens in response body for service-to-service auth.

    Args:
        user: User model
        db: Database session
        response: FastAPI Response object (optional, for setting cookies)

    Returns:
        LoginResponse with tokens
    """
    # Update last login (use naive datetime for DB compatibility)
    user.last_login = datetime.utcnow()
    await db.commit()

    # Get user roles from database
    db_roles = await get_user_roles(db, user.id)

    # Build role list (include type-based roles + database roles)
    roles = ["authenticated"]
    if user.is_superuser:
        roles.append("PlatformAdmin")
    else:
        roles.append("OrgUser")
    roles.extend(db_roles)

    # Build JWT claims with user info
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name or user.email.split("@")[0],
        "user_type": user.user_type.value,
        "is_superuser": user.is_superuser,
        "org_id": str(user.organization_id) if user.organization_id else None,
        "roles": roles,
    }

    # Generate tokens
    access_token = create_access_token(data=token_data)
    refresh_token_str, jti = create_refresh_token(data={"sub": str(user.id)})

    # Store JTI in Redis for revocation support
    await store_refresh_token_jti(str(user.id), jti)

    # Set cookies for browser clients
    if response:
        set_auth_cookies(response, access_token, refresh_token_str)

    logger.info(
        f"User logged in: {user.email}",
        extra={
            "user_id": str(user.id),
            "user_type": user.user_type.value,
            "is_superuser": user.is_superuser,
            "org_id": str(user.organization_id) if user.organization_id else None,
        }
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    request: Request,
    response: Response,
    token_data: TokenRefresh | None = None,
    db: DbSession = None,
) -> Token:
    """
    Refresh access token using refresh token with rotation.

    Implements refresh token rotation: the old token is invalidated
    and a new one is issued. This limits the window for token theft.

    Fetches fresh user data and roles from database to ensure
    the new token has up-to-date claims.

    The refresh token can be provided in two ways:
    1. Request body (API clients): {"refresh_token": "..."}
    2. HttpOnly cookie (browser clients): Automatically sent

    Rate limited: 10 requests per minute per IP address.

    Args:
        request: FastAPI request object
        token_data: Optional refresh token in body (API clients)
        db: Database session

    Returns:
        New access and refresh tokens with updated claims

    Raises:
        HTTPException: If refresh token is invalid or revoked
    """
    # Rate limiting
    client_ip = get_client_ip(request)
    await auth_limiter.check("refresh", client_ip)

    # Get refresh token from body (API clients) or cookie (browser clients)
    refresh_token_value = None
    if token_data and token_data.refresh_token:
        refresh_token_value = token_data.refresh_token
    else:
        refresh_token_value = request.cookies.get("refresh_token")

    if not refresh_token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Decode with type validation
    payload = decode_token(refresh_token_value, expected_type="refresh")

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    jti = payload.get("jti")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate JTI exists and revoke it (single use - rotation)
    if not jti:
        # Legacy token without JTI - reject
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jti_valid = await validate_and_revoke_refresh_token_jti(user_id, jti)
    if not jti_valid:
        # JTI not found - token was already used or revoked
        logger.warning(f"Refresh token reuse attempt for user {user_id}, JTI {jti}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked or already used",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify user still exists and is active
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(UUID(user_id))

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get fresh user roles from database
    db_roles = await get_user_roles(db, user.id)

    # Build role list
    roles = ["authenticated"]
    if user.is_superuser:
        roles.append("PlatformAdmin")
    else:
        roles.append("OrgUser")
    roles.extend(db_roles)

    # Build JWT claims with fresh user info
    new_token_data = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name or user.email.split("@")[0],
        "user_type": user.user_type.value,
        "is_superuser": user.is_superuser,
        "org_id": str(user.organization_id) if user.organization_id else None,
        "roles": roles,
    }

    # Generate new tokens with rotation
    access_token = create_access_token(data=new_token_data)
    new_refresh_token, new_jti = create_refresh_token(data={"sub": str(user.id)})

    # Store new JTI in Redis
    await store_refresh_token_jti(str(user.id), new_jti)

    # Set cookies for browser clients
    set_auth_cookies(response, access_token, new_refresh_token)

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: CurrentActiveUser,
) -> UserResponse:
    """
    Get current authenticated user information.

    Returns user info including type, organization, and roles from the JWT token.

    Args:
        current_user: Current authenticated user (from JWT)

    Returns:
        User information with roles
    """
    return UserResponse(
        id=str(current_user.user_id),
        email=current_user.email,
        name=current_user.name,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        is_verified=current_user.is_verified,
        user_type=current_user.user_type,
        organization_id=str(current_user.organization_id) if current_user.organization_id else None,
        roles=current_user.roles,
    )


class LogoutResponse(BaseModel):
    """Logout response model."""
    message: str = "Logged out successfully"


class RevokeAllResponse(BaseModel):
    """Revoke all sessions response model."""
    message: str
    sessions_revoked: int


class LogoutRequest(BaseModel):
    """Logout request with optional refresh token."""
    refresh_token: str | None = None


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    response: Response,
    current_user: CurrentActiveUser,
    body: LogoutRequest | None = None,
) -> LogoutResponse:
    """
    Logout current user and revoke refresh token.

    Clears authentication cookies and revokes the current refresh token.
    The access token will remain valid until expiry (30 minutes max).

    For API clients using Bearer auth, the refresh_token should be passed
    in the request body. For browser clients using cookies, the token is
    read from the refresh_token cookie automatically.

    Args:
        request: FastAPI request (to get refresh token cookie)
        response: FastAPI response (to clear cookies)
        current_user: Current authenticated user
        body: Optional request body containing refresh_token for API clients

    Returns:
        Logout confirmation
    """
    # Get refresh token from body (API clients) or cookie (browser clients)
    refresh_token = None
    if body and body.refresh_token:
        refresh_token = body.refresh_token
    else:
        refresh_token = request.cookies.get("refresh_token")

    if refresh_token:
        payload = decode_token(refresh_token, expected_type="refresh")
        if payload and payload.get("jti"):
            await validate_and_revoke_refresh_token_jti(
                str(current_user.user_id),
                payload["jti"]
            )

    # Clear cookies
    clear_auth_cookies(response)

    logger.info(f"User logged out: {current_user.email}")

    return LogoutResponse()


@router.post("/revoke-all", response_model=RevokeAllResponse)
async def revoke_all_sessions(
    response: Response,
    current_user: CurrentActiveUser,
) -> RevokeAllResponse:
    """
    Revoke all refresh tokens for the current user.

    This logs out all sessions across all devices. Useful when:
    - User suspects account compromise
    - User wants to sign out everywhere
    - Password has been changed

    Note: Access tokens will remain valid until expiry (30 minutes max).
    For immediate revocation, consider also changing the password.

    Args:
        response: FastAPI response (to clear current cookies)
        current_user: Current authenticated user

    Returns:
        Number of sessions revoked
    """
    count = await revoke_all_user_refresh_tokens(str(current_user.user_id))

    # Clear cookies for current session
    clear_auth_cookies(response)

    logger.info(
        f"User revoked all sessions: {current_user.email}",
        extra={"sessions_revoked": count}
    )

    return RevokeAllResponse(
        message=f"All sessions have been revoked",
        sessions_revoked=count,
    )


class AdminRevokeRequest(BaseModel):
    """Admin revocation request."""
    user_id: str


@router.post("/admin/revoke-user", response_model=RevokeAllResponse)
async def admin_revoke_user_sessions(
    revoke_data: AdminRevokeRequest,
    current_user: CurrentActiveUser,
    db: DbSession,
) -> RevokeAllResponse:
    """
    Revoke all refresh tokens for a specific user (admin only).

    Allows platform administrators to forcibly log out a user from all
    devices. Useful for security incidents or account compromises.

    Requires platform admin (superuser) privileges.

    Args:
        revoke_data: Target user ID to revoke
        current_user: Current authenticated user (must be admin)
        db: Database session

    Returns:
        Number of sessions revoked

    Raises:
        HTTPException: If not admin or user not found
    """
    # Require platform admin
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin privileges required",
        )

    # Verify target user exists
    user_repo = UserRepository(db)
    target_user = await user_repo.get_by_id(revoke_data.user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Revoke all sessions for target user
    count = await revoke_all_user_refresh_tokens(revoke_data.user_id)

    logger.warning(
        f"Admin revoked all sessions for user: {target_user.email}",
        extra={
            "admin_user": current_user.email,
            "target_user": target_user.email,
            "target_user_id": revoke_data.user_id,
            "sessions_revoked": count,
        }
    )

    return RevokeAllResponse(
        message=f"All sessions have been revoked for user {target_user.email}",
        sessions_revoked=count,
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    request: Request,
    user_data: UserCreate,
    db: DbSession = None,
) -> UserResponse:
    """
    Register a new user with auto-provisioning.

    Handles three scenarios:
    1. Pre-created user (is_registered=False): Admin created the user, user completes registration
    2. First user in system: Becomes PlatformAdmin
    3. New user with matching domain: Auto-joined to organization

    Note: In production, this should be restricted or require admin approval.

    Rate limited: 10 requests per minute per IP address.

    Args:
        request: FastAPI request object
        user_data: User registration data
        db: Database session

    Returns:
        Created user information with roles

    Raises:
        HTTPException: If email already registered or provisioning fails
    """
    # Rate limiting
    client_ip = get_client_ip(request)
    await auth_limiter.check("register", client_ip)

    settings = get_settings()

    # Only allow registration in development or testing mode
    if not (settings.is_development or settings.is_testing):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User registration is disabled",
        )

    user_repo = UserRepository(db)

    # Check if email already exists
    existing_user = await user_repo.get_by_email(user_data.email)

    if existing_user:
        # Check if this is a pre-created user completing registration
        if not existing_user.is_registered:
            # Pre-created user - complete their registration
            existing_user.hashed_password = get_password_hash(user_data.password)
            existing_user.is_registered = True
            if user_data.name:
                existing_user.name = user_data.name
            await db.commit()

            logger.info(
                f"Pre-created user completed registration: {existing_user.email}",
                extra={
                    "user_id": str(existing_user.id),
                    "user_type": existing_user.user_type.value,
                }
            )

            # Build roles list
            roles = ["authenticated"]
            if existing_user.is_superuser:
                roles.append("PlatformAdmin")
            else:
                roles.append("OrgUser")

            return UserResponse(
                id=str(existing_user.id),
                email=existing_user.email,
                name=existing_user.name or "",
                is_active=existing_user.is_active,
                is_superuser=existing_user.is_superuser,
                is_verified=existing_user.is_verified,
                user_type=existing_user.user_type.value,
                organization_id=str(existing_user.organization_id) if existing_user.organization_id else None,
                roles=roles,
            )
        else:
            # Already registered user
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    # New user - use provisioning logic to determine user type and org assignment
    try:
        result = await ensure_user_provisioned(
            db=db,
            email=user_data.email,
            name=user_data.name,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Set password and mark as registered
    user = result.user
    user.hashed_password = get_password_hash(user_data.password)
    user.is_registered = True
    await db.commit()

    logger.info(
        f"User registered: {user.email}",
        extra={
            "user_id": str(user.id),
            "user_type": result.user_type.value,
            "was_created": result.was_created,
        }
    )

    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name or "",
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        is_verified=user.is_verified,
        user_type=result.user_type.value,
        organization_id=str(user.organization_id) if user.organization_id else None,
        roles=result.roles,
    )


@router.get("/status", response_model=AuthStatusResponse)
async def get_auth_status(db: DbSession = None) -> AuthStatusResponse:
    """
    Get authentication system status for the login page.

    Public endpoint that returns everything needed to render the login UI:
    - Whether this is first-time setup (no users exist)
    - Available authentication methods (password, OAuth providers)
    - MFA requirements

    Returns:
        AuthStatusResponse with complete login page configuration
    """
    from src.services.oauth_sso import OAuthService

    settings = get_settings()
    user_repo = UserRepository(db)
    has_users = await user_repo.has_any_users()

    # Get available OAuth providers
    oauth_service = OAuthService(db)
    available_providers = oauth_service.get_available_providers()

    # Provider display info
    provider_info_map = {
        "microsoft": {"display_name": "Microsoft", "icon": "microsoft"},
        "google": {"display_name": "Google", "icon": "google"},
        "oidc": {"display_name": "SSO", "icon": "key"},
    }

    oauth_providers = [
        OAuthProviderInfo(
            name=name,
            display_name=provider_info_map.get(name, {}).get("display_name", name.title()),
            icon=provider_info_map.get(name, {}).get("icon"),
        )
        for name in available_providers
    ]

    return AuthStatusResponse(
        needs_setup=not has_users,
        password_login_enabled=True,  # Always enabled for now
        mfa_required_for_password=settings.mfa_enabled,
        oauth_providers=oauth_providers,
    )


# NOTE: /auth/oauth/login endpoint was removed for security reasons.
# It accepted unverified email claims which allowed account takeover.
# Use /auth/oauth/callback flow instead which properly validates OAuth tokens.
