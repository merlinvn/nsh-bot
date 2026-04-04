"""API routers."""
from app.api.routers.health import router as health_router
from app.api.routers.internal import router as internal_router
from app.api.routers.webhooks import router as webhooks_router

__all__ = ["health_router", "internal_router", "webhooks_router"]
