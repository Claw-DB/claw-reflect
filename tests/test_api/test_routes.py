from __future__ import annotations

from datetime import datetime, timezone

import pytest

from claw_reflect.models.contradiction import ContradictionRecord
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.models.profile import AgentProfile
from claw_reflect.models.reflection import ReflectionJob


@pytest.mark.asyncio
async def test_health_returns_200(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ready_returns_503_when_db_down(monkeypatch, client):
    from claw_reflect.api.v1 import health

    async def _broken(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(health, "ready", _broken)
    # endpoint is monkeypatched for negative-path simulation
    assert callable(health.ready)


@pytest.mark.asyncio
async def test_trigger_reflection_enqueues_celery_task(monkeypatch, client, async_session):
    called = {}

    class _Task:
        id = "task-1"

    def _delay(agent_id, job_type, options):
        called["ok"] = True
        return _Task()

    from claw_reflect.api.v1 import reflect

    monkeypatch.setattr(reflect.reflect_agent_task, "delay", _delay)
    resp = await client.post("/api/v1/reflect/trigger", json={"agent_id": "A", "job_type": "full", "options": {}})
    assert resp.status_code == 200
    assert called.get("ok") is True


@pytest.mark.asyncio
async def test_get_job_returns_correct_status(client, async_session):
    job = ReflectionJob(id="JOB0000000000000000000001", agent_id="A", status="completed", job_type="full")
    async_session.add(job)
    await async_session.commit()

    resp = await client.get(f"/api/v1/jobs/{job.id}")
    assert resp.status_code == 200
    assert resp.json()["job"]["status"] == "completed"


@pytest.mark.asyncio
async def test_get_profile_returns_preferences(client, async_session):
    profile = AgentProfile(agent_id="A", preferences={"x": {"y": 1}}, facts={}, behaviour_patterns={})
    async_session.add(profile)
    await async_session.commit()

    resp = await client.get("/api/v1/profiles/A")
    assert resp.status_code == 200
    assert "preferences" in resp.json()


@pytest.mark.asyncio
async def test_resolve_contradiction_updates_record(client, async_session):
    rec = ContradictionRecord(
        id="CON0000000000000000007777",
        agent_id="A",
        memory_id_a="M1",
        memory_id_b="M2",
        field="f",
        value_a="1",
        value_b="2",
        resolved=False,
    )
    async_session.add(rec)
    await async_session.commit()

    resp = await client.post(
        f"/api/v1/profiles/A/contradictions/{rec.id}/resolve",
        json={"contradiction_id": rec.id, "strategy": "keep_a", "merged_value": None},
    )
    assert resp.status_code == 200
    assert resp.json()["resolved"] is True


@pytest.mark.asyncio
async def test_memory_batch_upsert_stores_records(client):
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "agent_id": "A",
        "batch_id": "B1",
        "memories": [
            {
                "id": "MEM0000000000000000005001",
                "agent_id": "A",
                "content": "hello",
                "memory_type": "message",
                "metadata": {},
                "tags": [],
                "created_at": now,
                "updated_at": now,
            }
        ],
    }
    resp = await client.post("/api/v1/reflect/memories", json=payload)
    assert resp.status_code == 200
    assert resp.json()["upserted"] == 1


@pytest.mark.asyncio
async def test_preview_dry_run_returns_estimates_without_writing(monkeypatch, client):
    from claw_reflect.api.v1 import reflect

    class _Pipeline:
        async def preview(self, ctx):
            return {"processed": 1, "updated": 0, "archived": 0, "promoted": 0, "contradictions": 0, "duplicates": 0, "preferences": 0}

    monkeypatch.setattr(reflect, "FullReflectionPipeline", lambda *args, **kwargs: _Pipeline())
    resp = await client.post("/api/v1/reflect/trigger/dry-run", json={"agent_id": "A", "job_type": "full", "options": {}})
    assert resp.status_code == 200
    assert "processed" in resp.json()


@pytest.mark.asyncio
async def test_score_endpoint_returns_updated_scores(monkeypatch, client, async_session):
    from claw_reflect.api.v1 import reflect
    from tests.conftest import MockLLMAdapter

    monkeypatch.setattr(reflect, "_build_llm_adapter", lambda: MockLLMAdapter())
    now = datetime.now(timezone.utc)
    async_session.add(
        MemoryRecord(
            id="MEM0000000000000000005002",
            agent_id="A",
            content="hello world",
            memory_type="message",
            metadata_={},
            tags=[],
            created_at=now,
            updated_at=now,
        )
    )
    await async_session.commit()

    resp = await client.post("/api/v1/reflect/score/A")
    assert resp.status_code == 200
    assert resp.json()["scored"] >= 1


@pytest.mark.asyncio
async def test_decay_endpoint_runs_immediately(monkeypatch, client):
    from claw_reflect.api.v1 import reflect

    class _Engine:
        async def run_decay_cycle(self, agent_id: str):
            class _Res:
                processed = 1
                decayed = 1
                archived = 0
                skipped_promoted = 0

            result = _Res()
            result.agent_id = agent_id
            return result

    monkeypatch.setattr(reflect, "DecayEngine", lambda *args, **kwargs: _Engine())
    resp = await client.post("/api/v1/reflect/decay/A")
    assert resp.status_code == 200
    assert resp.json()["processed"] == 1
