from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from claw_reflect.schemas.jobs import JobTriggerRequest
from claw_reflect.schemas.memory import MemoryBatch, MemoryRecordIn


def test_valid_payload_passes() -> None:
    now = datetime.now(UTC)
    payload = MemoryBatch(
        agent_id="agent_1",
        batch_id="batch_1",
        memories=[
            MemoryRecordIn(
                id="MEM0000000000000000000001",
                agent_id="agent_1",
                content="safe content",
                memory_type="message",
                metadata={},
                tags=[],
                created_at=now,
                updated_at=now,
            )
        ],
    )
    assert payload.agent_id == "agent_1"


def test_agent_id_with_special_chars_fails() -> None:
    with pytest.raises(ValidationError):
        JobTriggerRequest(agent_id="bad!*id", job_type="full", options={})


def test_oversized_content_fails() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        MemoryRecordIn(
            id="MEM0000000000000000000001",
            agent_id="agent_1",
            content="x" * 70000,
            memory_type="message",
            metadata={},
            tags=[],
            created_at=now,
            updated_at=now,
        )
