"""Admin prompts management router."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_admin_user, get_db
from app.api.schemas.prompt import PromptCreate, PromptResponse, PromptUpdate, VersionCreate
from app.models.admin_user import AdminUser
from app.models.prompt import Prompt

router = APIRouter(prefix="/admin/prompts", tags=["admin:prompts"])


@router.get("")
async def list_prompts(db: AsyncSession = Depends(get_db)):
    """List all prompts."""
    result = await db.execute(select(Prompt).order_by(Prompt.name))
    prompts = result.scalars().all()
    return [
        {"name": p.name, "description": None, "active_version": int(p.active_version)} for p in prompts
    ]


@router.post("")
async def create_prompt(body: PromptCreate, db: AsyncSession = Depends(get_db)):
    """Create a new prompt."""
    existing = await db.execute(select(Prompt).where(Prompt.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Prompt already exists")
    prompt = Prompt(
        name=body.name,
        template=body.template,
        description=body.description or "",
        active_version="1",
        versions=[{"version": 1, "template": body.template}],
    )
    db.add(prompt)
    await db.commit()
    return {"name": prompt.name, "active_version": 1}


@router.get("/{name}")
async def get_prompt(name: str, db: AsyncSession = Depends(get_db)):
    """Get prompt detail."""
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"name": prompt.name, "description": prompt.description, "active_version": int(prompt.active_version)}


@router.put("/{name}")
async def update_prompt(name: str, body: PromptUpdate, db: AsyncSession = Depends(get_db)):
    """Update prompt template (creates new version)."""
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    # Parse current versions
    current_versions = prompt.versions or []
    max_version = max((v.get("version", 0) for v in current_versions), default=0)
    new_version = max_version + 1

    # Add new version
    current_versions.append({"version": new_version, "template": body.template})
    prompt.versions = current_versions
    prompt.template = body.template
    prompt.active_version = str(new_version)
    if body.description:
        prompt.description = body.description
    await db.commit()
    return {"name": prompt.name, "active_version": new_version}


@router.delete("/{name}")
async def delete_prompt(name: str, db: AsyncSession = Depends(get_db)):
    """Delete a prompt."""
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    await db.delete(prompt)
    await db.commit()
    return {"ok": True}


@router.post("/{name}/versions")
async def create_version(name: str, body: VersionCreate, db: AsyncSession = Depends(get_db)):
    """Create a new version of a prompt."""
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    current_versions = prompt.versions or []
    max_version = max((v.get("version", 0) for v in current_versions), default=0)
    new_version = max_version + 1

    template = body.template if body.template else prompt.template
    current_versions.append({"version": new_version, "template": template})
    prompt.versions = current_versions
    await db.commit()
    return {"version": new_version}


@router.post("/{name}/activate")
async def activate_version(name: str, body: VersionCreate, db: AsyncSession = Depends(get_db)):
    """Activate a specific version."""
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    # Check version exists
    current_versions = prompt.versions or []
    if not any(v.get("version") == body.version for v in current_versions):
        raise HTTPException(status_code=404, detail="Version not found")

    prompt.active_version = str(body.version)
    await db.commit()
    return {"name": name, "active_version": body.version}


@router.get("/{name}/versions")
async def list_versions(name: str, db: AsyncSession = Depends(get_db)):
    """List all versions of a prompt."""
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    versions = prompt.versions or []
    current_active = int(prompt.active_version)
    return [
        {
            "version": v.get("version"),
            "template": v.get("template"),
            "created_at": prompt.updated_at.isoformat(),
            "active": v.get("version") == current_active,
        }
        for v in versions
    ]
