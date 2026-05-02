from __future__ import annotations

import asyncio
import uuid

import pytest
from blake3 import blake3
from fastapi import HTTPException
from starlette.requests import Request

from claw_reflect.auth import get_api_key
from claw_reflect.models.api_key import ApiKey


def _request_with_key(key: str | None) -> Request:
    headers = []
    if key is not None:
        headers.append((b"x-claw-api-key", key.encode("utf-8")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
    }
    return Request(scope)


def _patch_session_factory(monkeypatch, async_session) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from claw_reflect import auth

    factory = async_sessionmaker(async_session.bind, expire_on_commit=False, class_=AsyncSession)

    class _CM:
        async def __aenter__(self):
            self._session = factory()
            return self._session

        async def __aexit__(self, exc_type, exc, tb):
            await self._session.close()
            return False

    monkeypatch.setattr(auth, "session_factory", lambda: _CM())


@pytest.mark.asyncio
async def test_valid_key_passes(async_session, monkeypatch):
    ws = uuid.UUID("11111111-1111-1111-1111-111111111111")
    raw = "valid-test-key"
    async_session.add(
        ApiKey(
            key_hash=blake3(raw.encode("utf-8")).hexdigest(),
            workspace_id=ws,
            label="test",
            revoked=False,
        )
    )
    await async_session.commit()

    _patch_session_factory(monkeypatch, async_session)
    monkeypatch.setattr(asyncio, "create_task", lambda coro: asyncio.get_running_loop().create_task(coro))

    request = _request_with_key(raw)
    returned = await get_api_key(request)
    assert returned == raw
    assert request.state.workspace_id == ws


@pytest.mark.asyncio
async def test_revoked_key_returns_401(async_session, monkeypatch):
    _patch_session_factory(monkeypatch, async_session)
    raw = "revoked-key"
    async_session.add(
        ApiKey(
            key_hash=blake3(raw.encode("utf-8")).hexdigest(),
            workspace_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            label="revoked",
            revoked=True,
        )
    )
    await async_session.commit()

    request = _request_with_key(raw)
    with pytest.raises(HTTPException) as exc:
        await get_api_key(request)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_wrong_key_returns_401(async_session, monkeypatch):
    _patch_session_factory(monkeypatch, async_session)
    request = _request_with_key("bad-key")
    with pytest.raises(HTTPException) as exc:
        await get_api_key(request)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_header_returns_401():
    request = _request_with_key(None)
    with pytest.raises(HTTPException) as exc:
        await get_api_key(request)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_last_used_at_is_updated_async(async_session, monkeypatch):
    _patch_session_factory(monkeypatch, async_session)
    raw = "touch-key"
    row = ApiKey(
        key_hash=blake3(raw.encode("utf-8")).hexdigest(),
        workspace_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        label="touch",
        revoked=False,
    )
    async_session.add(row)
    await async_session.commit()

    request = _request_with_key(raw)
    await get_api_key(request)
    await asyncio.sleep(0.05)
    await async_session.refresh(row)
    assert row.last_used_at is not None
