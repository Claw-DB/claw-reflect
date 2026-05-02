"""API v1 router — combines all v1 sub-routers into a single include."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from claw_reflect.api.v1 import health, jobs, profiles, reflect
from claw_reflect.auth import get_api_key

v1_router = APIRouter()

v1_router.include_router(health.router, tags=["health"])
v1_router.include_router(
    reflect.router,
    prefix="/reflect",
    tags=["reflect"],
    dependencies=[Depends(get_api_key)],
)
v1_router.include_router(
    jobs.router,
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(get_api_key)],
)
v1_router.include_router(
    profiles.router,
    prefix="/profiles",
    tags=["profiles"],
    dependencies=[Depends(get_api_key)],
)
