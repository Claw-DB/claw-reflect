"""Normalize legacy workspace IDs and make agent profiles workspace-scoped.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-05 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SENTINEL_WORKSPACE_ID = "00000000-0000-0000-0000-000000000000"
TABLES_WITH_WORKSPACE = (
    "memory_records",
    "reflection_jobs",
    "reflection_results",
    "extracted_preferences",
    "agent_profiles",
    "contradiction_records",
    "decay_records",
)


def _normalize_workspace_ids() -> None:
    for table_name in TABLES_WITH_WORKSPACE:
        op.execute(
            sa.text(
                f"""
                UPDATE {table_name}
                SET workspace_id = :sentinel
                WHERE workspace_id IS NULL
                   OR workspace_id NOT IN (SELECT workspace_id FROM api_keys)
                """
            ).bindparams(sentinel=SENTINEL_WORKSPACE_ID)
        )


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    _normalize_workspace_ids()

    if dialect_name == "postgresql":
        op.execute("ALTER TABLE agent_profiles DROP CONSTRAINT IF EXISTS agent_profiles_pkey")
        op.execute("ALTER TABLE agent_profiles ADD CONSTRAINT pk_agent_profiles PRIMARY KEY (workspace_id, agent_id)")
    else:
        op.create_unique_constraint("uq_agent_profiles_workspace_agent", "agent_profiles", ["workspace_id", "agent_id"])


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == "postgresql":
        op.execute("ALTER TABLE agent_profiles DROP CONSTRAINT IF EXISTS pk_agent_profiles")
        op.execute("ALTER TABLE agent_profiles ADD CONSTRAINT agent_profiles_pkey PRIMARY KEY (agent_id)")
    else:
        op.drop_constraint("uq_agent_profiles_workspace_agent", "agent_profiles", type_="unique")
