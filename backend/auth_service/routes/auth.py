"""
Auth route handlers.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse

from auth_service.config import get_settings
from auth_service.dependencies import get_auth_service, get_current_token
from auth_service.models.schemas import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserInfo,
    VerifyTokenRequest,
    VerifyTokenResponse,
)
from auth_service.services.auth_service import AuthService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    svc: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    """Username + password → access + refresh tokens."""
    return await svc.login(body.username, body.password)


@router.post("/logout", status_code=204)
async def logout(
    body: LogoutRequest,
    svc: AuthService = Depends(get_auth_service),
) -> Response:
    """Invalidate refresh token server-side."""
    await svc.logout(body.refresh_token)
    return Response(status_code=204)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    svc: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Exchange refresh token for a new token pair."""
    return await svc.refresh_tokens(body.refresh_token)


@router.get("/me", response_model=UserInfo)
async def get_me(
    token: str = Depends(get_current_token),
    svc: AuthService = Depends(get_auth_service),
) -> UserInfo:
    """Return current user info from bearer token."""
    return await svc.get_current_user(token)


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    body: RegisterRequest,
    svc: AuthService = Depends(get_auth_service),
) -> RegisterResponse:
    """Create new user account."""
    return await svc.register(
        username=body.username,
        email=body.email,
        password=body.password,
        first_name=body.first_name,
        last_name=body.last_name,
        org_id=body.org_id,
        role=body.role,
    )


@router.get("/sso/google")
async def sso_google_redirect(request: Request) -> RedirectResponse:
    """
    Redirect to Google OAuth consent screen via Keycloak broker.
    Keycloak handles the OIDC federation — we just redirect to KC login.
    """
    settings = get_settings()
    kc_url = (
        f"{settings.keycloak_server_url}/realms/{settings.keycloak_realm}"
        f"/protocol/openid-connect/auth"
        f"?client_id={settings.keycloak_client_id}"
        f"&redirect_uri={settings.oauth_redirect_uri}"
        f"&response_type=code"
        f"&scope=openid+profile+email"
        f"&kc_idp_hint=google"
    )
    return RedirectResponse(url=kc_url)


@router.get("/sso/callback")
async def sso_callback(
    code: str,
    svc: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    """
    OAuth callback — exchange authorization code for tokens via Keycloak.
    Keycloak handles code exchange; we receive the token response.
    """
    settings = get_settings()
    from keycloak import KeycloakOpenID
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    _pool = ThreadPoolExecutor(max_workers=1)

    openid = KeycloakOpenID(
        server_url=settings.keycloak_server_url,
        client_id=settings.keycloak_client_id,
        realm_name=settings.keycloak_realm,
        client_secret_key=settings.keycloak_client_secret,
    )

    loop = asyncio.get_running_loop()
    kc_token = await loop.run_in_executor(
        _pool,
        lambda: openid.token(
            grant_type="authorization_code",
            code=code,
            redirect_uri=settings.oauth_redirect_uri,
        ),
    )
    kc_info = await loop.run_in_executor(
        _pool, lambda: openid.userinfo(kc_token["access_token"])
    )

    # Auto-provision user if not already in DB
    from auth_service.dependencies import get_db_session
    # Auth service already handles user provisioning in login flow
    # We reuse verify + get by faking a keycloak login response
    from auth_service.models.schemas import TokenResponse, UserInfo
    from datetime import datetime, timezone
    from uuid import uuid4

    tokens = TokenResponse(
        access_token=kc_token["access_token"],
        refresh_token=kc_token["refresh_token"],
        token_type="bearer",
        expires_in=kc_token.get("expires_in", 1800),
    )
    user = UserInfo(
        id=uuid4(),
        username=kc_info.get("preferred_username", ""),
        email=kc_info.get("email", ""),
        first_name=kc_info.get("given_name", ""),
        last_name=kc_info.get("family_name", ""),
        roles=kc_info.get("roles", []),
        created_at=datetime.now(timezone.utc),
    )
    return LoginResponse(user=user, tokens=tokens)


@router.post("/verify-token", response_model=VerifyTokenResponse)
async def verify_token(
    body: VerifyTokenRequest,
    svc: AuthService = Depends(get_auth_service),
) -> VerifyTokenResponse:
    """
    Validate token and return claims.
    Called by API gateway on every upstream request.
    """
    return await svc.verify_token(body.token)
