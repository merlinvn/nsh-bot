#!/usr/bin/env python
"""Bootstrap script to create or update an admin user."""
import argparse
import asyncio
import sys
import uuid
from datetime import datetime, timezone

import bcrypt

from app.core.database import async_session_context
from app.models.admin_user import AdminUser
from sqlalchemy import select


async def create_admin(username: str, password: str):
    """Create an admin user. Fails if one already exists."""
    async with async_session_context() as db:
        result = await db.execute(select(AdminUser))
        existing = result.scalars().first()
        if existing:
            print("ERROR: Admin user already exists. Bootstrap aborted.", file=sys.stderr)
            sys.exit(1)

        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
        admin = AdminUser(
            id=uuid.uuid4(),
            username=username,
            password_hash=password_hash,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(admin)
        await db.commit()
        print(f"Admin user '{username}' created successfully.")


async def upsert_admin(username: str, password: str):
    """Create or update an admin user (idempotent)."""
    async with async_session_context() as db:
        result = await db.execute(select(AdminUser).where(AdminUser.username == username))
        existing = result.scalars().first()

        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
        if existing:
            existing.password_hash = password_hash
            existing.is_active = True
            existing.updated_at = datetime.now(timezone.utc)
            await db.commit()
            print(f"Admin user '{username}' password updated.")
        else:
            admin = AdminUser(
                id=uuid.uuid4(),
                username=username,
                password_hash=password_hash,
                is_active=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(admin)
            await db.commit()
            print(f"Admin user '{username}' created.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create or update admin user")
    parser.add_argument("--username", default="admin", help="Admin username")
    parser.add_argument("--password", required=True, help="Admin password")
    parser.add_argument("--update", action="store_true", help="Update existing user (idempotent)")
    args = parser.parse_args()

    if args.update:
        asyncio.run(upsert_admin(args.username, args.password))
    else:
        asyncio.run(create_admin(args.username, args.password))
