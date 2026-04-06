#!/usr/bin/env python
"""Bootstrap script to create the initial admin user."""
import argparse
import asyncio
import sys
import uuid
from datetime import datetime, timezone

import bcrypt

from app.core.database import async_session_maker
from app.models.admin_user import AdminUser


async def create_admin(username: str, password: str):
    """Create an admin user."""
    async with async_session_maker() as db:
        # Check if any admin exists
        from sqlalchemy import select

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create initial admin user")
    parser.add_argument("--username", default="admin", help="Admin username")
    parser.add_argument("--password", required=True, help="Admin password")
    args = parser.parse_args()
    asyncio.run(create_admin(args.username, args.password))
