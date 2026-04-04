"""Tests for the Prompt model."""
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from app.models.prompt import Prompt


class TestPrompt:
    """Tests for Prompt ORM model."""

    async def test_create_prompt_with_name(self, session):
        """Can create a prompt with name (unique)."""
        prompt = Prompt(
            name="customer_greeting",
            template="Hello {{customer_name}}, how can I help you?",
            versions=[],
            active_version="v1",
        )
        session.add(prompt)
        await session.commit()

        assert prompt.id is not None
        assert prompt.name == "customer_greeting"
        assert prompt.template is not None
        assert prompt.created_at is not None

    async def test_name_is_unique(self, session):
        """Duplicate name raises IntegrityError."""
        prompt1 = Prompt(
            name="unique_prompt",
            template="Template 1",
            versions=[],
            active_version="v1",
        )
        session.add(prompt1)
        await session.commit()

        prompt2 = Prompt(
            name="unique_prompt",
            template="Template 2",
            versions=[],
            active_version="v1",
        )
        session.add(prompt2)
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_versions_stored_as_jsonb_array(self, session):
        """versions is stored as JSONB array."""
        prompt = Prompt(
            name="versioned_prompt",
            template="Current template",
            versions=[
                {"version": "v1", "text": "Original text", "created_by": "admin"},
                {"version": "v2", "text": "Updated text", "created_by": "admin"},
            ],
            active_version="v2",
        )
        session.add(prompt)
        await session.commit()

        await session.refresh(prompt)
        assert len(prompt.versions) == 2
        assert prompt.versions[0]["version"] == "v1"
        assert prompt.versions[1]["version"] == "v2"

    async def test_active_version_tracks_current_active(self, session):
        """active_version tracks which version is currently active."""
        prompt = Prompt(
            name="active_tracking",
            template="Active template",
            versions=[{"version": "v1", "text": "v1 text"}],
            active_version="v1",
        )
        session.add(prompt)
        await session.commit()

        assert prompt.active_version == "v1"

    async def test_can_add_new_version_to_versions_array(self, session):
        """Can add a new version to the versions array."""
        prompt = Prompt(
            name="add_version",
            template="Original",
            versions=[{"version": "v1", "text": "v1 text"}],
            active_version="v1",
        )
        session.add(prompt)
        await session.commit()

        new_version = {
            "version": "v2",
            "text": "v2 text",
            "created_by": "product_manager",
        }
        prompt.versions.append(new_version)
        prompt.active_version = "v2"
        flag_modified(prompt, "versions")
        await session.commit()

        await session.refresh(prompt)
        assert len(prompt.versions) == 2
        assert prompt.active_version == "v2"
        v2_data = next(v for v in prompt.versions if v["version"] == "v2")
        assert v2_data["text"] == "v2 text"

    async def test_can_activate_different_version(self, session):
        """Can switch active_version to a different version."""
        prompt = Prompt(
            name="switch_version",
            template="Switchable template",
            versions=[
                {"version": "v1", "text": "v1 text"},
                {"version": "v2", "text": "v2 text"},
                {"version": "v3", "text": "v3 text"},
            ],
            active_version="v1",
        )
        session.add(prompt)
        await session.commit()

        # Activate v3
        prompt.active_version = "v3"
        await session.commit()
        await session.refresh(prompt)
        assert prompt.active_version == "v3"

        # Switch back to v2
        prompt.active_version = "v2"
        await session.commit()
        await session.refresh(prompt)
        assert prompt.active_version == "v2"

    async def test_versions_default_to_empty_list(self, session):
        """versions defaults to empty list."""
        prompt = Prompt(
            name="default_versions",
            template="Template without versions",
            active_version="v1",
        )
        session.add(prompt)
        await session.commit()

        await session.refresh(prompt)
        assert prompt.versions == []

    async def test_query_by_name(self, session):
        """Can query prompt by name."""
        prompt = Prompt(
            name="findable_prompt",
            template="Find me!",
            versions=[],
            active_version="v1",
        )
        session.add(prompt)
        await session.commit()

        stmt = select(Prompt).where(Prompt.name == "findable_prompt")
        result = await session.execute(stmt)
        found = result.scalar_one_or_none()

        assert found is not None
        assert found.template == "Find me!"
