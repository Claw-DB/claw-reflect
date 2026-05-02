"""Bootstrap utility to generate and store a new API key hash."""

from __future__ import annotations

import argparse
import asyncio
import base64
import secrets
import uuid

from blake3 import blake3
from sqlalchemy import insert

from claw_reflect.db.session import session_factory
from claw_reflect.models.api_key import ApiKey


def build_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser."""
    parser = argparse.ArgumentParser(description="Create a claw-reflect API key")
    parser.add_argument("--label", required=True, help="Human-readable key label")
    parser.add_argument("--workspace-id", required=True, type=uuid.UUID, help="Workspace UUID")
    return parser


def generate_raw_key() -> str:
    """Generate a cryptographically random 32-byte base64url key."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")


async def create_key(label: str, workspace_id: uuid.UUID) -> str:
    """Persist API key hash and return raw key for one-time display."""
    raw_key = generate_raw_key()
    key_hash = blake3(raw_key.encode("utf-8")).hexdigest()

    async with session_factory() as session:
        await session.execute(
            insert(ApiKey).values(
                key_hash=key_hash,
                workspace_id=workspace_id,
                label=label,
                revoked=False,
            )
        )
        await session.commit()

    return raw_key


def main() -> None:
    """CLI entrypoint."""
    args = build_parser().parse_args()
    raw_key = asyncio.run(create_key(args.label, args.workspace_id))
    print("WARNING: Store this key now. It will not be shown again.")
    print(raw_key)


if __name__ == "__main__":
    main()
