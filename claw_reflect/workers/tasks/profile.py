"""Celery task for rebuilding the aggregated AgentProfile from reflected memories."""

import asyncio
from collections import Counter, defaultdict
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from claw_reflect.db.session import session_factory
from claw_reflect.metrics.instruments import agent_profile_version, profile_updated_total
from claw_reflect.models.memory import MemoryRecord
from claw_reflect.models.preference import ExtractedPreference
from claw_reflect.models.profile import AgentProfile
from claw_reflect.workers.celery_app import celery_app


@celery_app.task(name="claw_reflect.workers.tasks.profile.update_profile_task")
def update_profile_task(
    workspace_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, object]:
    """Rebuild profile preferences/facts for one agent or all agents."""

    async def _run() -> dict[str, object]:
        async with session_factory() as session:
            workspace_uuid = UUID(workspace_id) if workspace_id else None
            if agent_id and workspace_uuid is not None:
                targets = [(workspace_uuid, agent_id)]
            elif agent_id:
                result = await session.execute(
                    select(MemoryRecord.workspace_id, MemoryRecord.agent_id).where(MemoryRecord.agent_id == agent_id).distinct()
                )
                targets = [(row[0], row[1]) for row in result.all()]
            else:
                stmt = select(MemoryRecord.workspace_id, MemoryRecord.agent_id).distinct()
                if workspace_uuid:
                    stmt = stmt.where(MemoryRecord.workspace_id == workspace_uuid)
                result = await session.execute(stmt)
                targets = [(row[0], row[1]) for row in result.all()]

            updated = 0
            for target_workspace, target_agent in targets:
                pref_stmt = select(ExtractedPreference).where(
                    ExtractedPreference.agent_id == target_agent,
                    ExtractedPreference.workspace_id == target_workspace,
                    ExtractedPreference.is_active.is_(True),
                )
                prefs_result = await session.execute(pref_stmt)
                active_prefs = list(prefs_result.scalars().all())
                preference_map: dict[str, dict[str, object]] = defaultdict(dict)
                for pref in active_prefs:
                    preference_map[pref.category][pref.key] = pref.value

                memory_stmt = select(MemoryRecord).where(
                    MemoryRecord.agent_id == target_agent,
                    MemoryRecord.workspace_id == target_workspace,
                )
                memories_result = await session.execute(memory_stmt)
                memories = list(memories_result.scalars().all())
                type_counts = Counter(memory.memory_type for memory in memories)

                profile_stmt = select(AgentProfile).where(
                    AgentProfile.agent_id == target_agent,
                    AgentProfile.workspace_id == target_workspace,
                )
                profile_result = await session.execute(profile_stmt)
                profile = profile_result.scalar_one_or_none()
                now = datetime.now(UTC)
                if profile is None:
                    profile = AgentProfile(
                        workspace_id=target_workspace,
                        agent_id=target_agent,
                        preferences=dict(preference_map),
                        facts={"memory_type_counts": dict(type_counts)},
                        behaviour_patterns={},
                        last_updated_at=now,
                        memory_count=len(memories),
                        profile_version=1,
                    )
                    session.add(profile)
                else:
                    profile.preferences = dict(preference_map)
                    profile.facts = {"memory_type_counts": dict(type_counts)}
                    profile.profile_version += 1
                    profile.last_updated_at = now
                    profile.memory_count = len(memories)

                profile_updated_total.labels(agent_id=target_agent).inc()
                agent_profile_version.labels(agent_id=target_agent).set(profile.profile_version)
                updated += 1

            await session.commit()
        return {"updated_profiles": updated, "workspace_id": workspace_id, "agent_id": agent_id}

    return asyncio.run(_run())
