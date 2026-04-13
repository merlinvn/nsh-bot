"""Admin routers."""
from app.api.routers.admin.analytics import router as analytics_router
from app.api.routers.admin.auth import router as auth_router
from app.api.routers.admin.conversations import router as conversations_router
from app.api.routers.admin.playground import router as playground_router
from app.api.routers.admin.prompts import router as prompts_router
from app.api.routers.admin.zalo_tokens import router as zalo_tokens_router
from app.api.routers.admin.zalo_users import router as zalo_users_router
from app.api.routers.admin.monitoring import router as monitoring_router

__all__ = [
    "auth_router",
    "prompts_router",
    "conversations_router",
    "analytics_router",
    "playground_router",
    "zalo_tokens_router",
    "zalo_users_router",
    "monitoring_router",
]
