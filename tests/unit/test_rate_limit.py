from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_eleventh_request_is_rate_limited(client, monkeypatch):
    from claw_reflect.api.v1 import reflect

    class _Task:
        id = "task-1"

    monkeypatch.setattr(reflect.reflect_agent_task, "delay", lambda *args, **kwargs: _Task())

    payload = {"agent_id": "agent_1", "job_type": "full", "options": {}}
    statuses = []
    for _ in range(11):
        resp = await client.post("/api/v1/reflect/trigger", json=payload)
        statuses.append(resp.status_code)

    assert statuses[-1] == 429
