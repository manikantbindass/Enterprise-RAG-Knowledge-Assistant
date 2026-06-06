"""
Auth business logic — orchestrates Keycloak + local JWT + DB.

Strategy:
  - If Keycloak is enabled → Keycloak is source of truth for tokens
  - If Keycloak disabled (dev) → local bcrypt + JWT + Redis
  - User record always synced to local DB for fast lookups
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.config import get_settings
from auth_service.exceptions import (
    AuthenticationError,
    InvalidCredentialsError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from auth_service.models.schemas import (
    LoginResponse,
    RegisterResponse,
    TokenResponse,
    UserInfo,
    VerifyTokenResponse,
)
from auth_service.repositories.user_repository import UserModel, UserRepository
from auth_service.services.jwt_service import JWTService
from auth_service.services.keycloak_service import KeycloakService

logger = structlog.get_logger(__name__)

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash_password(password: str) -> str:
    return _pwd_ctx.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


def _user_model_to_info(user: UserModel) -> UserInfo:
    return UserInfo(
        id=user.id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        org_id=user.org_id,
        roles=list(user.roles or []),
        is_active=user.is_active,
        created_at=user.created_at,
    )


class AuthService:
    """
    Main auth orchestrator.
    Injected: db session, jwt service, keycloak service.
    """

    def __init__(
        self,
        session: AsyncSession,
        jwt_svc: JWTService,
        keycloak_svc: KeycloakService,
    ) -> None:
        self._session = session
        self._jwt = jwt_svc
        self._kc = keycloak_svc
        self._settings = get_settings()

    # ── Login ──────────────────────────────────────────────────────────────

    async def login(self, username: str, password: str) -> LoginResponse:
        repo = UserRepository(self._session)
        user = await repo.get_by_username(username)

        if self._settings.keycloak_enabled:
            return await self._login_keycloak(user, username, password)
        else:
            return await self._login_local(user, password)

    async def _login_keycloak(
        self, user: UserModel | None, username: str, password: str
    ) -> LoginResponse:
        kc_token = await self._kc.get_token(username, password)
        kc_info = await self._kc.get_userinfo(kc_token["access_token"])

        repo = UserRepository(self._session)
        if user is None:
            # First login — auto-provision local user record
            user = await repo.create(
                username=username,
                email=kc_info.get("email", ""),
                hashed_password=None,
                first_name=kc_info.get("given_name", ""),
                last_name=kc_info.get("family_name", ""),
                keycloak_id=kc_info.get("sub"),
            )
            await self._session.commit()
        elif user.keycloak_id is None:
            await repo.update_keycloak_id(user.id, kc_info.get("sub", ""))
            await self._session.commit()

        tokens = TokenResponse(
            access_token=kc_token["access_token"],
            refresh_token=kc_token["refresh_token"],
            token_type="bearer",
            expires_in=kc_token.get("expires_in", 1800),
        )
        return LoginResponse(user=_user_model_to_info(user), tokens=tokens)

    async def _login_local(
        self, user: UserModel | None, password: str
    ) -> LoginResponse:
        if user is None or not user.hashed_password:
            raise InvalidCredentialsError()
        if not _verify_password(password, user.hashed_password):
            raise InvalidCredentialsError()
        if not user.is_active:
            raise AuthenticationError("Account is disabled")

        access_token, expire = self._jwt.create_access_token(
            user_id=user.id,
            username=user.username,
            org_id=user.org_id,
            roles=list(user.roles or []),
        )
        refresh_token = await self._jwt.create_refresh_token(user.id)

        tokens = TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=self._settings.access_token_expire_minutes * 60,
        )
        return LoginResponse(user=_user_model_to_info(user), tokens=tokens)

    # ── Refresh ────────────────────────────────────────────────────────────

    async def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        if self._settings.keycloak_enabled:
            kc_token = await self._kc.refresh_token(refresh_token)
            return TokenResponse(
                access_token=kc_token["access_token"],
                refresh_token=kc_token["refresh_token"],
                token_type="bearer",
                expires_in=kc_token.get("expires_in", 1800),
            )
        else:
            user_id = await self._jwt.verify_refresh_token(refresh_token)
            await self._jwt.revoke_refresh_token(refresh_token)

            repo = UserRepository(self._session)
            user = await repo.get_by_id(user_id)
            access_token, _ = self._jwt.create_access_token(
                user_id=user.id,
                username=user.username,
                org_id=user.org_id,
                roles=list(user.roles or []),
            )
            new_refresh = await self._jwt.create_refresh_token(user.id)
            return TokenResponse(
                access_token=access_token,
                refresh_token=new_refresh,
                token_type="bearer",
                expires_in=self._settings.access_token_expire_minutes * 60,
            )

    # ── Logout ─────────────────────────────────────────────────────────────

    async def logout(self, refresh_token: str) -> None:
        if self._settings.keycloak_enabled:
            await self._kc.logout(refresh_token)
        else:
            await self._jwt.revoke_refresh_token(refresh_token)

    # ── Register ───────────────────────────────────────────────────────────

    async def register(
        self,
        username: str,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        org_id: UUID | None = None,
        role: str = "viewer",
    ) -> RegisterResponse:
        repo = UserRepository(self._session)

        keycloak_id: str | None = None
        if self._settings.keycloak_enabled:
            keycloak_id = await self._kc.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                attributes={"org_id": str(org_id)} if org_id else {},
            )
            await self._kc.assign_role(keycloak_id, role)

        hashed = _hash_password(password) if not self._settings.keycloak_enabled else None
        user = await repo.create(
            username=username,
            email=email,
            hashed_password=hashed,
            first_name=first_name,
            last_name=last_name,
            org_id=org_id,
            roles=[role],
            keycloak_id=keycloak_id,
        )
        await self._session.commit()
        return RegisterResponse(user=_user_model_to_info(user))

    # ── Token verification ─────────────────────────────────────────────────

    async def verify_token(self, token: str) -> VerifyTokenResponse:
        if self._settings.keycloak_enabled:
            try:
                info = await self._kc.verify_token(token)
                return VerifyTokenResponse(
                    valid=True,
                    user_id=UUID(info["sub"]) if info.get("sub") else None,
                    username=info.get("preferred_username"),
                    org_id=None,
                    roles=info.get("realm_access", {}).get("roles", []),
                )
            except Exception:
                return VerifyTokenResponse(valid=False)
        else:
            try:
                claims = self._jwt.verify_access_token(token)
                return VerifyTokenResponse(
                    valid=True,
                    user_id=UUID(claims["sub"]),
                    username=claims.get("username"),
                    org_id=UUID(claims["org_id"]) if claims.get("org_id") else None,
                    roles=claims.get("roles", []),
                    expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
                )
            except Exception:
                return VerifyTokenResponse(valid=False)

    # ── Current user ───────────────────────────────────────────────────────

    async def get_current_user(self, token: str) -> UserInfo:
        repo = UserRepository(self._session)
        if self._settings.keycloak_enabled:
            info = await self._kc.get_userinfo(token)
            user = await repo.get_by_keycloak_id(info["sub"])
            if user is None:
                raise UserNotFoundError(info.get("sub", "unknown"))
        else:
            claims = self._jwt.verify_access_token(token)
            user = await repo.get_by_id(UUID(claims["sub"]))
        return _user_model_to_info(user)
