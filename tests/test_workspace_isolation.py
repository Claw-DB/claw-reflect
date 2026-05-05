from __future__ import annotations

import uuid

import pytest
from blake3 import blake3
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from claw_reflect.main import app
from claw_reflect.models.api_key import ApiKey
from claw_reflect.models.profile import AgentProfile
from claw_reflect.models.reflection import ReflectionJob


@pytest.mark.asyncio
async def test_workspace_a_trigger_does_not_touch_workspace_b(async_session: AsyncSession, monkeypatch):
    from claw_reflect import auth
    from claw_reflect.api.v1 import reflect
    from claw_reflect.db.session import get_session

    workspace_a = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    workspace_b = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    agent_id = "shared_agent"
    key_a = "workspace-a-key"
    key_b = "workspace-b-key"

    factory = async_sessionmaker(async_session.bind, expire_on_commit=False, class_=AsyncSession)

    class _CM:
        async def __aenter__(self):
            self._session = factory()
            return self._session

        async def __aexit__(self, exc_type, exc, tb):
            await self._session.close()
            return False

    auth.session_factory = lambda: _CM()

    async def _override_get_session():
        yield async_session

    class _Task:
        id = "task-1"

    monkeypatch.setattr(reflect.reflect_agent_task, "delay", lambda *args, **kwargs: _Task())

    async_session.add_all(
        [
            ApiKey(key_hash=blake3(key_a.encode("utf-8")).hexdigest(), workspace_id=workspace_a, label="a"),
            ApiKey(key_hash=blake3(key_b.encode("utf-8")).hexdigest(), workspace_id=workspace_b, label="b"),
            AgentProfile(
                workspace_id=workspace_b,
                agent_id=agent_id,
                preferences={},
                facts={"workspace": "b"},
                behaviour_patterns={},
                memory_count=0,
                profile_version=1,
            ),
        ]
    )
    await async_session.commit()

    app.dependency_overrides[get_session] = _override_get_session
    try:
        async with (
            AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://test",
                headers={"X-Claw-Api-Key": key_a},
            ) as client_a,
            AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://test",
                headers={"X-Claw-Api-Key": key_b},
            ) as client_b,
        ):
            now = "2026-05-05T00:00:00+00:00"
            payload_a = {
                "agent_id": agent_id,
                "batch_id": "batch-a",
                "memories": [
                    {
                        "id": "MEMA000000000000000000001",
                        "agent_id": agent_id,
                        "content": "workspace a memory",
                        "memory_type": "message",
                        "metadata": {},
                        "tags": [],
                        "created_at": now,
                        "updated_at": now,
                    }
                ],
            }
            payload_b = {
                "agent_id": agent_id,
                "batch_id": "batch-b",
                "memories": [
                    {
                        "id": "MEMB000000000000000000001",
                        "agent_id": agent_id,
                        "content": "workspace b memory",
                        "memory_type": "message",
                        "metadata": {},
                        "tags": [],
                        "created_at": now,
                        "updated_at": now,
                    }
                ],
            }

            ingest_a = await client_a.post("/api/v1/reflect/memories", json=payload_a)
            ingest_b = await client_b.post("/api/v1/reflect/memories", json=payload_b)
            assert ingest_a.status_code == 200
            assert ingest_b.status_code == 200

            trigger = await client_a.post(
                "/api/v1/reflect/trigger",
                json={"agent_id": agent_id, "job_type": "full", "options": {}},
            )
            assert trigger.status_code == 200

        jobs_a = await async_session.execute(select(ReflectionJob).where(ReflectionJob.workspace_id == workspace_a))
        jobs_b = await async_session.execute(select(ReflectionJob).where(ReflectionJob.workspace_id == workspace_b))
        profile_b = await async_session.scalar(
            select(AgentProfile).where(
                AgentProfile.workspace_id == workspace_b,
                AgentProfile.agent_id == agent_id,
            )
        )

        assert len(list(jobs_a.scalars().all())) == 1
        assert list(jobs_b.scalars().all()) == []
        assert profile_b is not None
        assert profile_b.facts == {"workspace": "b"}
        assert profile_b.profile_version == 1
    finally:
        app.dependency_overrides.clear()
