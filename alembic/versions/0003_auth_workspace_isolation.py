"""Add API keys and workspace isolation.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-02 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


TABLES_WITH_WORKSPACE = [
    "memory_records",
    "reflection_jobs",
    "reflection_results",
    "extracted_preferences",
    "agent_profiles",
    "contradiction_records",
    "decay_records",
]


def _workspace_server_default(dialect_name: str) -> str:
    if dialect_name == "postgresql":
        return "gen_random_uuid()"
    return "'00000000-0000-0000-0000-000000000000'"


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "api_keys",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            nullable=False,
            server_default=sa.text(_workspace_server_default(dialect_name)),
        ),
        sa.Column("key_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_workspace_active", "api_keys", ["workspace_id"], postgresql_where=sa.text("NOT revoked"))

    default_sql = _workspace_server_default(dialect_name)
    for table_name in TABLES_WITH_WORKSPACE:
        op.add_column(
            table_name,
            sa.Column("workspace_id", sa.Uuid(), nullable=False, server_default=sa.text(default_sql)),
        )
        op.create_index(f"ix_{table_name}_workspace_id", table_name, ["workspace_id"])
        op.create_check_constraint(
            f"ck_{table_name}_workspace_id_not_null",
            table_name,
            "workspace_id IS NOT NULL",
        )


def downgrade() -> None:
    for table_name in reversed(TABLES_WITH_WORKSPACE):
        op.drop_constraint(f"ck_{table_name}_workspace_id_not_null", table_name, type_="check")
        op.drop_index(f"ix_{table_name}_workspace_id", table_name=table_name)
        op.drop_column(table_name, "workspace_id")

    op.drop_index("ix_api_keys_workspace_active", table_name="api_keys")
    op.drop_table("api_keys")
