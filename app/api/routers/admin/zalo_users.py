"""Admin Zalo user management router."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_admin_user, get_db
from app.models.admin_user import AdminUser
from app.models.zalo_user import ZaloUser

router = APIRouter(prefix="/admin/zalo-users", tags=["admin:zalo-users"])


@router.get("")
async def list_zalo_users(db: AsyncSession = Depends(get_db)):
    """List all Zalo users."""
    result = await db.execute(select(ZaloUser).order_by(ZaloUser.created_at.desc()))
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "user_id": u.user_id,
            "display_name": u.display_name,
            "user_alias": u.user_alias,
            "avatar": u.avatar,
            "user_is_follower": u.user_is_follower,
            "user_last_interaction_date": u.user_last_interaction_date,
            "user_external_id": u.user_external_id,
            "user_id_by_app": u.user_id_by_app,
            "shared_info": u.shared_info,
            "tags_and_notes_info": u.tags_and_notes_info,
            "is_sensitive": u.is_sensitive,
            "last_fetched_at": u.last_fetched_at.isoformat() if u.last_fetched_at else None,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


@router.get("/{user_id}")
async def get_zalo_user(user_id: str, db: AsyncSession = Depends(get_db)):
    """Get a Zalo user by user_id."""
    result = await db.execute(select(ZaloUser).where(ZaloUser.user_id == user_id))
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": str(u.id),
        "user_id": u.user_id,
        "display_name": u.display_name,
        "user_alias": u.user_alias,
        "avatar": u.avatar,
        "user_is_follower": u.user_is_follower,
        "user_last_interaction_date": u.user_last_interaction_date,
        "user_external_id": u.user_external_id,
        "user_id_by_app": u.user_id_by_app,
        "shared_info": u.shared_info,
        "tags_and_notes_info": u.tags_and_notes_info,
        "is_sensitive": u.is_sensitive,
        "last_fetched_at": u.last_fetched_at.isoformat() if u.last_fetched_at else None,
        "created_at": u.created_at.isoformat(),
        "updated_at": u.updated_at.isoformat(),
    }
