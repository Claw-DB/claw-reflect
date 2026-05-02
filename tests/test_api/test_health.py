"""Tests for health, readiness, and metrics API endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "timestamp" in response.json()
    assert response.json()["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_ready_returns_ready(client: AsyncClient) -> None:
    response = await client.get("/api/v1/ready")
    assert response.status_code in (200, 503)


@pytest.mark.asyncio
async def test_metrics_returns_prometheus_format(client: AsyncClient) -> None:
    response = await client.get("/api/v1/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
