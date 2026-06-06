"""
Routes package — collect and export all routers.
"""

from __future__ import annotations

from routes.admin import router as admin_router
from routes.auth import router as auth_router
from routes.chat import router as chat_router
from routes.documents import router as documents_router
from routes.health import router as health_router
from routes.organizations import router as organizations_router
from routes.search import router as search_router
from routes.users import router as users_router

__all__ = [
    "admin_router",
    "auth_router",
    "chat_router",
    "documents_router",
    "health_router",
    "organizations_router",
    "search_router",
    "users_router",
]
