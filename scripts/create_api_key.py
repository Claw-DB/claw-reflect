"""Create and persist a new claw-reflect API key for a workspace."""

from __future__ import annotations

import argparse
import asyncio
import base64
import secrets
import uuid

from blake3 import blake3

from claw_reflect.db.session import session_factory
from claw_reflect.models.api_key import ApiKey


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a claw-reflect API key")
    parser.add_argument("--workspace-id", required=True, help="Workspace UUID that the key should map to")
    parser.add_argument("--label", default=None, help="Optional human-readable label for the key")
    return parser.parse_args()


def generate_api_key() -> str:
    raw = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
    return raw.rstrip("=")


async def main() -> None:
    args = parse_args()
    workspace_id = uuid.UUID(args.workspace_id)
    raw_key = generate_api_key()

    async with session_factory() as session:
        session.add(
            ApiKey(
                key_hash=blake3(raw_key.encode("utf-8")).hexdigest(),
                workspace_id=workspace_id,
                label=args.label,
            )
        )
        await session.commit()

    print(raw_key)


if __name__ == "__main__":
    asyncio.run(main())
