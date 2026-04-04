"""Tests for health check endpoints (GET /health/live, GET /health/ready)."""
import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.main import app


@pytest.fixture
def client() -> TestClient:
    """Return a synchronous TestClient for the FastAPI app."""
    return TestClient(app, raise_server_exceptions=False)


class TestHealthLive:
    """Test cases for GET /health/live."""

    def test_live_always_returns_alive(self, client: TestClient) -> None:
        """Liveness probe always returns 200 with status 'alive', regardless of dependencies."""
        # No need to mock anything — liveness has no dependencies
        response = client.get("/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"


class TestHealthReady:
    """Test cases for GET /health/ready."""

    def test_ready_all_healthy(self, client: TestClient) -> None:
        """When all health checks pass, endpoint returns 200 with status 'ready'."""
        with (
            patch("app.api.routers.health.check_db_health", new_callable=AsyncMock, return_value=True),
            patch("app.api.routers.health.check_redis_health", new_callable=AsyncMock, return_value=True),
            patch("app.api.routers.health.check_rabbitmq_health", new_callable=AsyncMock, return_value=True),
        ):
            response = client.get("/health/ready")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert "postgresql" in data["checks"]
            assert data["checks"]["postgresql"]["status"] == "ok"
            assert "redis" in data["checks"]
            assert data["checks"]["redis"]["status"] == "ok"
            assert "rabbitmq" in data["checks"]
            assert data["checks"]["rabbitmq"]["status"] == "ok"

    def test_ready_postgres_down(self, client: TestClient) -> None:
        """When PostgreSQL is unreachable, endpoint returns 503 with degraded status."""
        with (
            patch("app.api.routers.health.check_db_health", new_callable=AsyncMock, return_value=False),
            patch("app.api.routers.health.check_redis_health", new_callable=AsyncMock, return_value=True),
            patch("app.api.routers.health.check_rabbitmq_health", new_callable=AsyncMock, return_value=True),
        ):
            response = client.get("/health/ready")

            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"
            assert data["checks"]["postgresql"]["status"] == "error"
            assert data["checks"]["redis"]["status"] == "ok"
            assert data["checks"]["rabbitmq"]["status"] == "ok"

    def test_ready_redis_down(self, client: TestClient) -> None:
        """When Redis is unreachable, endpoint returns 503 with degraded status."""
        with (
            patch("app.api.routers.health.check_db_health", new_callable=AsyncMock, return_value=True),
            patch("app.api.routers.health.check_redis_health", new_callable=AsyncMock, return_value=False),
            patch("app.api.routers.health.check_rabbitmq_health", new_callable=AsyncMock, return_value=True),
        ):
            response = client.get("/health/ready")

            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"
            assert data["checks"]["postgresql"]["status"] == "ok"
            assert data["checks"]["redis"]["status"] == "error"
            assert data["checks"]["rabbitmq"]["status"] == "ok"

    def test_ready_rabbitmq_down(self, client: TestClient) -> None:
        """When RabbitMQ is unreachable, endpoint returns 503 with degraded status."""
        with (
            patch("app.api.routers.health.check_db_health", new_callable=AsyncMock, return_value=True),
            patch("app.api.routers.health.check_redis_health", new_callable=AsyncMock, return_value=True),
            patch("app.api.routers.health.check_rabbitmq_health", new_callable=AsyncMock, return_value=False),
        ):
            response = client.get("/health/ready")

            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"
            assert data["checks"]["postgresql"]["status"] == "ok"
            assert data["checks"]["redis"]["status"] == "ok"
            assert data["checks"]["rabbitmq"]["status"] == "error"

    def test_ready_all_down(self, client: TestClient) -> None:
        """When all services are down, endpoint returns 503 with all checks in error."""
        with (
            patch("app.api.routers.health.check_db_health", new_callable=AsyncMock, return_value=False),
            patch("app.api.routers.health.check_redis_health", new_callable=AsyncMock, return_value=False),
            patch("app.api.routers.health.check_rabbitmq_health", new_callable=AsyncMock, return_value=False),
        ):
            response = client.get("/health/ready")

            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"
            assert data["checks"]["postgresql"]["status"] == "error"
            assert data["checks"]["redis"]["status"] == "error"
            assert data["checks"]["rabbitmq"]["status"] == "error"
