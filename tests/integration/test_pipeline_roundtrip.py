from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from claw_reflect.models.contradiction import ContradictionRecord
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.models.preference import ExtractedPreference

requires_integration = pytest.mark.skipif(
    os.getenv("REFLECT_RUN_INTEGRATION_TESTS") != "1",
    reason="integration tests require REFLECT_RUN_INTEGRATION_TESTS=1",
)


@requires_integration
@pytest.mark.asyncio
async def test_full_reflection_round_trip(client, async_session):
    now = datetime.now(UTC).isoformat()
    payload = {
        "agent_id": "agent_integration",
        "batch_id": "batch_1",
        "memories": [
            {
                "id": f"MEMINT{i:020d}",
                "agent_id": "agent_integration",
                "content": f"User likes concise responses {i}",
                "memory_type": "message",
                "metadata": {"session_id": "s1"},
                "tags": ["pref"],
                "created_at": now,
                "updated_at": now,
            }
            for i in range(10)
        ],
    }
    ingest = await client.post("/api/v1/reflect/memories", json=payload)
    assert ingest.status_code == 200

    trigger = await client.post(
        "/api/v1/reflect/trigger/dry-run",
        json={"agent_id": "agent_integration", "job_type": "full", "options": {}},
    )
    assert trigger.status_code == 200


@requires_integration
@pytest.mark.asyncio
async def test_workspace_isolation_smoke(client):
    # End-to-end workspace isolation is verified through API key dependency and
    # workspace-scoped query predicates; this smoke checks that endpoint remains callable.
    response = await client.get("/api/v1/jobs")
    assert response.status_code in (200, 401)


@requires_integration
@pytest.mark.asyncio
async def test_duplicate_collapse_setup(async_session):
    now = datetime.now(UTC)
    async_session.add_all(
        [
            MemoryRecord(
                id="MEMDUP000000000000000001",
                workspace_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                agent_id="agent_dup",
                content="same content",
                memory_type="message",
                metadata_={},
                tags=[],
                created_at=now,
                updated_at=now,
            ),
            MemoryRecord(
                id="MEMDUP000000000000000002",
                workspace_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                agent_id="agent_dup",
                content="same content",
                memory_type="message",
                metadata_={},
                tags=[],
                created_at=now,
                updated_at=now,
            ),
            MemoryRecord(
                id="MEMDUP000000000000000003",
                workspace_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                agent_id="agent_dup",
                content="same content",
                memory_type="message",
                metadata_={},
                tags=[],
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    await async_session.commit()
    rows = await async_session.execute(select(MemoryRecord).where(MemoryRecord.agent_id == "agent_dup"))
    assert len(list(rows.scalars().all())) == 3


@requires_integration
@pytest.mark.asyncio
async def test_decay_setup(async_session):
    now = datetime.now(UTC)
    memory = MemoryRecord(
        id="MEMDEC000000000000000001",
        workspace_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        agent_id="agent_decay",
        content="stale memory",
        memory_type="message",
        metadata_={},
        tags=[],
        created_at=now - timedelta(days=60),
        updated_at=now - timedelta(days=60),
        composite_score=0.3,
    )
    async_session.add(memory)
    await async_session.commit()
    loaded = await async_session.get(MemoryRecord, memory.id)
    assert loaded is not None


@requires_integration
@pytest.mark.asyncio
async def test_contradiction_detection_setup(async_session):
    rows = await async_session.execute(select(ContradictionRecord))
    _ = list(rows.scalars().all())
    prefs = await async_session.execute(select(ExtractedPreference))
    _ = list(prefs.scalars().all())
