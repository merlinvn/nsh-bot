#!/usr/bin/env python3
"""Script to manually update Zalo access token and refresh token in the database.

Usage:
    uv run python app/api/scripts/update_zalo_token.py --access-token "new_access_token" --refresh-token "new_refresh_token"
"""
import argparse
import sys
from uuid import uuid4

sys.path.insert(0, ".")

from sqlalchemy import text
from app.workers.shared.db import db_session


async def update_zalo_token(access_token: str, refresh_token: str | None = None, expires_in_seconds: int = 90000) -> bool:
    """Update or create Zalo token in database.

    Args:
        access_token: New Zalo access token
        refresh_token: New Zalo refresh token (optional)
        expires_in_seconds: Token expiry time in seconds (default 90 seconds for testing)

    Returns:
        True if successful
    """
    from datetime import datetime, timedelta, timezone

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)

    async with db_session() as session:
        # Check if token exists
        result = await session.execute(text("SELECT id FROM zalo_tokens LIMIT 1"))
        row = result.fetchone()

        if row:
            token_id = row[0]
            if refresh_token:
                await session.execute(
                    text("""
                        UPDATE zalo_tokens
                        SET access_token = :access_token,
                            refresh_token = :refresh_token,
                            expires_at = :expires_at
                        WHERE id = :id
                    """),
                    {"access_token": access_token, "refresh_token": refresh_token, "expires_at": expires_at, "id": token_id}
                )
            else:
                await session.execute(
                    text("""
                        UPDATE zalo_tokens
                        SET access_token = :access_token, expires_at = :expires_at
                        WHERE id = :id
                    """),
                    {"access_token": access_token, "expires_at": expires_at, "id": token_id}
                )
            print(f"Updated existing token (id={token_id})")
        else:
            new_id = uuid4()
            if refresh_token:
                await session.execute(
                    text("""
                        INSERT INTO zalo_tokens (id, access_token, refresh_token, expires_at)
                        VALUES (:id, :access_token, :refresh_token, :expires_at)
                    """),
                    {"id": new_id, "access_token": access_token, "refresh_token": refresh_token, "expires_at": expires_at}
                )
            else:
                await session.execute(
                    text("""
                        INSERT INTO zalo_tokens (id, access_token, expires_at)
                        VALUES (:id, :access_token, :expires_at)
                    """),
                    {"id": new_id, "access_token": access_token, "expires_at": expires_at}
                )
            print(f"Created new token (id={new_id})")

    print(f"Access token updated. Expires at: {expires_at}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Update Zalo OAuth tokens in database")
    parser.add_argument("--access-token", required=True, help="New Zalo access token")
    parser.add_argument("--refresh-token", help="New Zalo refresh token (optional)")
    parser.add_argument("--expires-in", type=int, default=90000, help="Token expiry in seconds (default: 90000)")

    args = parser.parse_args()

    try:
        import asyncio
        asyncio.run(update_zalo_token(
            access_token=args.access_token,
            refresh_token=args.refresh_token,
            expires_in_seconds=args.expires_in
        ))
        print("Done!")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
