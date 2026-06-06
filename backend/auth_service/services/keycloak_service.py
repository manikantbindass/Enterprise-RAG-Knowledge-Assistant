"""
Keycloak admin/user operations via python-keycloak.
All Keycloak calls are synchronous (python-keycloak is sync);
we offload them to a thread pool to keep the async event loop free.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import UUID

import structlog
from keycloak import KeycloakAdmin, KeycloakOpenID
from keycloak.exceptions import KeycloakAuthenticationError, KeycloakGetError

from auth_service.config import get_settings
from auth_service.exceptions import (
    AuthenticationError,
    KeycloakUnavailableError,
    UserAlreadyExistsError,
    UserNotFoundError,
)

logger = structlog.get_logger(__name__)

_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="keycloak")


class KeycloakService:
    """
    Wrapper around python-keycloak.
    Lazy-initialises Keycloak clients on first use.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._openid: KeycloakOpenID | None = None
        self._admin: KeycloakAdmin | None = None

    def _get_openid(self) -> KeycloakOpenID:
        if self._openid is None:
            s = self._settings
            self._openid = KeycloakOpenID(
                server_url=s.keycloak_server_url,
                client_id=s.keycloak_client_id,
                realm_name=s.keycloak_realm,
                client_secret_key=s.keycloak_client_secret,
            )
        return self._openid

    def _get_admin(self) -> KeycloakAdmin:
        if self._admin is None:
            s = self._settings
            self._admin = KeycloakAdmin(
                server_url=s.keycloak_server_url,
                username=s.keycloak_admin_username,
                password=s.keycloak_admin_password,
                realm_name=s.keycloak_realm,
                verify=True,
            )
        return self._admin

    async def _run(self, fn, *args, **kwargs) -> Any:
        """Execute sync Keycloak call in thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_POOL, lambda: fn(*args, **kwargs))

    # ── Token operations ───────────────────────────────────────────────────

    async def get_token(self, username: str, password: str) -> dict[str, Any]:
        """Password-flow token acquisition."""
        try:
            openid = self._get_openid()
            token = await self._run(openid.token, username, password)
            logger.info("keycloak_token_issued", username=username)
            return token
        except KeycloakAuthenticationError as exc:
            raise AuthenticationError("Invalid username or password") from exc
        except Exception as exc:
            logger.exception("keycloak_get_token_failed", username=username)
            raise KeycloakUnavailableError(str(exc)) from exc

    async def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an existing token."""
        try:
            openid = self._get_openid()
            token = await self._run(openid.refresh_token, refresh_token)
            return token
        except KeycloakAuthenticationError as exc:
            raise AuthenticationError("Invalid or expired refresh token") from exc
        except Exception as exc:
            raise KeycloakUnavailableError(str(exc)) from exc

    async def logout(self, refresh_token: str) -> None:
        """Revoke refresh token (server-side logout)."""
        try:
            openid = self._get_openid()
            await self._run(openid.logout, refresh_token)
        except Exception as exc:
            logger.warning("keycloak_logout_error", error=str(exc))

    async def verify_token(self, token: str) -> dict[str, Any]:
        """Token introspection — returns claims dict if valid."""
        try:
            openid = self._get_openid()
            info = await self._run(openid.introspect, token)
            if not info.get("active", False):
                raise AuthenticationError("Token is inactive or expired")
            return info
        except AuthenticationError:
            raise
        except Exception as exc:
            raise KeycloakUnavailableError(str(exc)) from exc

    async def get_userinfo(self, token: str) -> dict[str, Any]:
        """Fetch user info from /userinfo endpoint."""
        try:
            openid = self._get_openid()
            return await self._run(openid.userinfo, token)
        except Exception as exc:
            raise KeycloakUnavailableError(str(exc)) from exc

    # ── User management ────────────────────────────────────────────────────

    async def create_user(
        self,
        username: str,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        attributes: dict[str, Any] | None = None,
    ) -> str:
        """Create user in Keycloak. Returns new user ID."""
        try:
            admin = self._get_admin()
            user_id = await self._run(
                admin.create_user,
                {
                    "username": username,
                    "email": email,
                    "firstName": first_name,
                    "lastName": last_name,
                    "enabled": True,
                    "credentials": [
                        {"type": "password", "value": password, "temporary": False}
                    ],
                    "attributes": attributes or {},
                },
            )
            logger.info("keycloak_user_created", username=username, user_id=user_id)
            return user_id
        except KeycloakGetError as exc:
            if "409" in str(exc):
                raise UserAlreadyExistsError(username) from exc
            raise KeycloakUnavailableError(str(exc)) from exc
        except Exception as exc:
            logger.exception("keycloak_create_user_failed", username=username)
            raise KeycloakUnavailableError(str(exc)) from exc

    async def get_user_by_id(self, user_id: str) -> dict[str, Any]:
        """Fetch Keycloak user by ID."""
        try:
            admin = self._get_admin()
            return await self._run(admin.get_user, user_id)
        except KeycloakGetError as exc:
            if "404" in str(exc):
                raise UserNotFoundError(user_id) from exc
            raise KeycloakUnavailableError(str(exc)) from exc

    async def update_user(self, user_id: str, payload: dict[str, Any]) -> None:
        """Update Keycloak user attributes."""
        try:
            admin = self._get_admin()
            await self._run(admin.update_user, user_id, payload)
        except Exception as exc:
            raise KeycloakUnavailableError(str(exc)) from exc

    async def delete_user(self, user_id: str) -> None:
        """Hard-delete user from Keycloak."""
        try:
            admin = self._get_admin()
            await self._run(admin.delete_user, user_id)
            logger.info("keycloak_user_deleted", user_id=user_id)
        except Exception as exc:
            raise KeycloakUnavailableError(str(exc)) from exc

    async def assign_role(self, user_id: str, role_name: str) -> None:
        """Assign realm role to user."""
        try:
            admin = self._get_admin()
            roles = await self._run(admin.get_realm_roles)
            role = next((r for r in roles if r["name"] == role_name), None)
            if role is None:
                logger.warning("keycloak_role_not_found", role=role_name)
                return
            await self._run(admin.assign_realm_roles, user_id, [role])
            logger.info("keycloak_role_assigned", user_id=user_id, role=role_name)
        except Exception as exc:
            raise KeycloakUnavailableError(str(exc)) from exc
