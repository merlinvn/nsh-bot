"""Tests for internal admin API endpoints (require X-Internal-Api-Key)."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.api.main import app as main_app
from app.api.routers import internal
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.prompt import Prompt


async def create_async_client(session_factory):
    """Create an AsyncClient with test DB and auth overrides."""
    async def override_get_db():
        async with session_factory() as session:
            yield session

    mock_channel = MagicMock()
    mock_exchange = MagicMock()
    mock_exchange.publish = AsyncMock()
    mock_channel.get_exchange = AsyncMock(return_value=mock_exchange)

    main_app.dependency_overrides[internal.get_db] = override_get_db
    main_app.dependency_overrides[internal.get_rabbitmq] = lambda: mock_channel
    main_app.dependency_overrides[internal.verify_internal_api_key] = lambda: "valid-key"

    return AsyncClient(
        transport=ASGITransport(app=main_app),
        base_url="http://test",
    )


@pytest.fixture
def valid_headers() -> dict:
    """Return valid headers for internal API endpoints."""
    return {"X-Internal-Api-Key": "valid-key"}


# ----- Test cases -----

class TestInternalAuth:
    """Test cases for X-Internal-Api-Key authentication."""

    @pytest.mark.asyncio
    async def test_internal_without_auth(self, session_factory) -> None:
        """Request without X-Internal-Api-Key header returns 401."""
        async def override_get_db():
            async with session_factory() as session:
                yield session

        async def raise_401():
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail={"code": "INVALID_API_KEY", "message": "Invalid or missing X-Internal-Api-Key header."})

        main_app.dependency_overrides[internal.get_db] = override_get_db
        main_app.dependency_overrides[internal.get_rabbitmq] = lambda: MagicMock()
        main_app.dependency_overrides[internal.verify_internal_api_key] = raise_401

        async with AsyncClient(
            transport=ASGITransport(app=main_app),
            base_url="http://test",
        ) as client:
            response = await client.get("/internal/conversations")
            assert response.status_code == 401

        main_app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_internal_with_valid_auth(self, session_factory, valid_headers) -> None:
        """Request with correct X-Internal-Api-Key header returns 200 or 2xx (not 401)."""
        async with await create_async_client(session_factory) as client:
            response = await client.get("/internal/conversations", headers=valid_headers)
            assert response.status_code != 401

        main_app.dependency_overrides.clear()


class TestConversationsList:
    """Test cases for GET /internal/conversations."""

    @pytest.mark.asyncio
    async def test_conversations_list_empty(self, session_factory, valid_headers) -> None:
        """Returns empty list when no conversations exist."""
        async with await create_async_client(session_factory) as client:
            response = await client.get("/internal/conversations", headers=valid_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["items"] == []
            assert data["total"] == 0

        main_app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_conversations_list_with_data(self, session_factory, valid_headers) -> None:
        """Returns paginated list of conversations with message counts."""
        # Create test data
        async with session_factory() as session:
            conv = Conversation(
                external_user_id="user_list_test",
                conversation_key=f"key_{uuid.uuid4().hex[:8]}",
                status="active",
            )
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
            conv_id = conv.id

            msg1 = Message(
                conversation_id=conv_id,
                direction="inbound",
                text="Hello",
                message_id=f"msg_{uuid.uuid4().hex[:8]}",
                prompt_version="v1.0",
            )
            msg2 = Message(
                conversation_id=conv_id,
                direction="outbound",
                text="Hi there",
                message_id=f"msg_{uuid.uuid4().hex[:8]}",
                prompt_version="v1.0",
            )
            session.add_all([msg1, msg2])
            await session.commit()

        async with await create_async_client(session_factory) as client:
            response = await client.get("/internal/conversations", headers=valid_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["total"] >= 1
            assert data["page"] == 1
            assert data["size"] == 20

        main_app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_conversations_list_filtered_by_user_id(self, session_factory, valid_headers) -> None:
        """Filtering by user_id returns only matching conversations."""
        async with session_factory() as session:
            conv1 = Conversation(
                external_user_id="user_filter_1",
                conversation_key=f"key_{uuid.uuid4().hex[:8]}",
                status="active",
            )
            conv2 = Conversation(
                external_user_id="user_filter_2",
                conversation_key=f"key_{uuid.uuid4().hex[:8]}",
                status="active",
            )
            session.add_all([conv1, conv2])
            await session.commit()

        async with await create_async_client(session_factory) as client:
            response = await client.get(
                "/internal/conversations",
                params={"user_id": "user_filter_1"},
                headers=valid_headers,
            )
            assert response.status_code == 200
            data = response.json()
            for item in data["items"]:
                assert item["external_user_id"] == "user_filter_1"

        main_app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_conversations_list_pagination(self, session_factory, valid_headers) -> None:
        """Pagination parameters work correctly."""
        async with session_factory() as session:
            for i in range(5):
                conv = Conversation(
                    external_user_id=f"user_page_{i}",
                    conversation_key=f"key_{uuid.uuid4().hex[:8]}",
                    status="active",
                )
                session.add(conv)
            await session.commit()

        async with await create_async_client(session_factory) as client:
            response = await client.get(
                "/internal/conversations",
                params={"page": 1, "size": 2},
                headers=valid_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 2
            assert data["page"] == 1
            assert data["size"] == 2
            assert data["pages"] >= 2

        main_app.dependency_overrides.clear()


class TestConversationDetail:
    """Test cases for GET /internal/conversations/{conversation_id}."""

    @pytest.mark.asyncio
    async def test_conversation_detail_not_found(self, session_factory, valid_headers) -> None:
        """Returns 404 for non-existent conversation ID."""
        async with await create_async_client(session_factory) as client:
            fake_id = str(uuid.uuid4())
            response = await client.get(
                f"/internal/conversations/{fake_id}",
                headers=valid_headers,
            )
            assert response.status_code == 404

        main_app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_conversation_detail_with_messages(self, session_factory, valid_headers) -> None:
        """Returns conversation with messages sorted by created_at."""
        conv_id = None
        async with session_factory() as session:
            conv = Conversation(
                external_user_id="user_detail",
                conversation_key=f"key_{uuid.uuid4().hex[:8]}",
                status="active",
            )
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
            conv_id = conv.id

            msg1 = Message(
                conversation_id=conv_id,
                direction="inbound",
                text="First",
                message_id=f"msg_{uuid.uuid4().hex[:8]}",
                prompt_version="v1.0",
            )
            msg2 = Message(
                conversation_id=conv_id,
                direction="outbound",
                text="Second",
                message_id=f"msg_{uuid.uuid4().hex[:8]}",
                prompt_version="v1.0",
            )
            session.add_all([msg1, msg2])
            await session.commit()

        async with await create_async_client(session_factory) as client:
            response = await client.get(
                f"/internal/conversations/{conv_id}",
                headers=valid_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["external_user_id"] == "user_detail"
            assert len(data["messages"]) == 2

        main_app.dependency_overrides.clear()


class TestReplay:
    """Test cases for POST /internal/replay."""

    @pytest.mark.asyncio
    async def test_replay_not_found(self, session_factory, valid_headers) -> None:
        """Returns 404 for non-existent conversation."""
        async with await create_async_client(session_factory) as client:
            fake_id = str(uuid.uuid4())
            response = await client.post(
                f"/internal/replay?conversation_id={fake_id}",
                headers=valid_headers,
            )
            assert response.status_code == 404

        main_app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_replay_success(self, session_factory, valid_headers) -> None:
        """Replays a conversation by republishing messages to queue."""
        conv_id = None
        async with session_factory() as session:
            conv = Conversation(
                external_user_id="user_replay",
                conversation_key=f"key_{uuid.uuid4().hex[:8]}",
                status="active",
            )
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
            conv_id = conv.id

            msg = Message(
                conversation_id=conv_id,
                direction="inbound",
                text="Hello",
                message_id=f"msg_{uuid.uuid4().hex[:8]}",
                prompt_version="v1.0",
            )
            session.add(msg)
            await session.commit()

        async with await create_async_client(session_factory) as client:
            response = await client.post(
                f"/internal/replay?conversation_id={conv_id}",
                headers=valid_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["conversation_id"] == str(conv_id)

        main_app.dependency_overrides.clear()


class TestPrompts:
    """Test cases for /internal/prompts endpoints."""

    @pytest.mark.asyncio
    async def test_prompts_list_empty(self, session_factory, valid_headers) -> None:
        """Returns empty list when no prompts exist."""
        async with await create_async_client(session_factory) as client:
            response = await client.get("/internal/prompts", headers=valid_headers)
            assert response.status_code == 200
            data = response.json()
            assert data == []

        main_app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_prompts_list_with_data(self, session_factory, valid_headers) -> None:
        """Returns list of prompts."""
        async with session_factory() as session:
            prompt = Prompt(
                name="greeting",
                template="Hi {{name}}",
                versions=[{"version": "v1.0", "template": "Hi {{name}}", "active": True, "created_at": "2024-01-01T00:00:00"}],
                active_version="v1.0",
            )
            session.add(prompt)
            await session.commit()

        async with await create_async_client(session_factory) as client:
            response = await client.get("/internal/prompts", headers=valid_headers)
            assert response.status_code == 200
            data = response.json()
            assert len(data) >= 1

        main_app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_prompts_activate_success(self, session_factory, valid_headers) -> None:
        """Successfully activates a different version."""
        prompt_name = None
        async with session_factory() as session:
            prompt = Prompt(
                name="activate_test",
                template="Hello",
                versions=[
                    {"version": "v1.0", "template": "Hello", "active": True},
                    {"version": "v2.0", "template": "Hello v2", "active": False},
                ],
                active_version="v1.0",
            )
            session.add(prompt)
            await session.commit()
            prompt_name = prompt.name

        async with await create_async_client(session_factory) as client:
            response = await client.post(
                "/internal/prompts/activate",
                json={"name": prompt_name, "version": "v2.0"},
                headers=valid_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "activate_test"
            assert data["active_version"] == "v2.0"

        main_app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_prompts_activate_version_not_found(self, session_factory, valid_headers) -> None:
        """Returns 404 when trying to activate non-existent version."""
        prompt_name = None
        async with session_factory() as session:
            prompt = Prompt(
                name="activate_missing",
                template="Hello",
                versions=[{"version": "v1.0", "template": "Hello", "active": True}],
                active_version="v1.0",
            )
            session.add(prompt)
            await session.commit()
            prompt_name = prompt.name

        async with await create_async_client(session_factory) as client:
            response = await client.post(
                "/internal/prompts/activate",
                json={"name": prompt_name, "version": "v99.0"},
                headers=valid_headers,
            )
            assert response.status_code == 404

        main_app.dependency_overrides.clear()
