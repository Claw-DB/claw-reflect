"""Initial schema migration — creates all claw-reflect tables with indexes.

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all initial tables and indexes."""
    # ------------------------------------------------------------------
    # memory_records
    # ------------------------------------------------------------------
    op.create_table(
        "memory_records",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("agent_id", sa.String(26), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("memory_type", sa.String(64), nullable=False),
        sa.Column("metadata", sa.JSON, nullable=False),
        sa.Column("tags", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("importance_score", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("recency_score", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("confidence_score", sa.Float, nullable=False, server_default="0.8"),
        sa.Column("composite_score", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("reflection_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("reflection_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_reflected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_promoted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ttl_override_days", sa.Integer, nullable=True),
    )
    op.create_index("ix_memory_records_agent_id", "memory_records", ["agent_id"])
    op.create_index("ix_memory_records_reflection_status", "memory_records", ["reflection_status"])
    op.create_index("ix_memory_records_composite_score", "memory_records", ["composite_score"])
    op.create_index("ix_memory_records_created_at", "memory_records", ["created_at"])

    # ------------------------------------------------------------------
    # reflection_jobs
    # ------------------------------------------------------------------
    op.create_table(
        "reflection_jobs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("agent_id", sa.String(26), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("job_type", sa.String(32), nullable=False, server_default="full"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("memories_processed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("memories_updated", sa.Integer, nullable=False, server_default="0"),
        sa.Column("memories_archived", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False),
    )
    op.create_index("ix_reflection_jobs_agent_id", "reflection_jobs", ["agent_id"])
    op.create_index("ix_reflection_jobs_status", "reflection_jobs", ["status"])
    op.create_index("ix_reflection_jobs_started_at", "reflection_jobs", ["started_at"])

    # ------------------------------------------------------------------
    # reflection_results
    # ------------------------------------------------------------------
    op.create_table(
        "reflection_results",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(26),
            sa.ForeignKey("reflection_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("memory_id", sa.String(26), nullable=False),
        sa.Column("result_type", sa.String(32), nullable=False),
        sa.Column("output", sa.JSON, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("applied", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("ix_reflection_results_job_id", "reflection_results", ["job_id"])
    op.create_index("ix_reflection_results_memory_id", "reflection_results", ["memory_id"])
    op.create_index("ix_reflection_results_result_type", "reflection_results", ["result_type"])

    # ------------------------------------------------------------------
    # extracted_preferences
    # ------------------------------------------------------------------
    op.create_table(
        "extracted_preferences",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("agent_id", sa.String(26), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value", sa.JSON, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("source_memory_ids", sa.JSON, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmation_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.UniqueConstraint("agent_id", "category", "key", name="uq_preference_agent_cat_key"),
    )
    op.create_index("ix_extracted_preferences_agent_id", "extracted_preferences", ["agent_id"])
    op.create_index("ix_extracted_preferences_is_active", "extracted_preferences", ["is_active"])

    # ------------------------------------------------------------------
    # contradiction_records
    # ------------------------------------------------------------------
    op.create_table(
        "contradiction_records",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("agent_id", sa.String(26), nullable=False),
        sa.Column("memory_id_a", sa.String(26), nullable=False),
        sa.Column("memory_id_b", sa.String(26), nullable=False),
        sa.Column("field", sa.String(128), nullable=False),
        sa.Column("value_a", sa.JSON, nullable=False),
        sa.Column("value_b", sa.JSON, nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("resolution_strategy", sa.String(32), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("winner_memory_id", sa.String(26), nullable=True),
    )
    op.create_index("ix_contradiction_records_agent_id", "contradiction_records", ["agent_id"])
    op.create_index("ix_contradiction_records_resolved", "contradiction_records", ["resolved"])
    op.create_index("ix_contradiction_records_detected_at", "contradiction_records", ["detected_at"])

    # ------------------------------------------------------------------
    # agent_profiles
    # ------------------------------------------------------------------
    op.create_table(
        "agent_profiles",
        sa.Column("agent_id", sa.String(26), primary_key=True),
        sa.Column("preferences", sa.JSON, nullable=False),
        sa.Column("facts", sa.JSON, nullable=False),
        sa.Column("behaviour_patterns", sa.JSON, nullable=False),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("memory_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("profile_version", sa.Integer, nullable=False, server_default="1"),
    )

    # ------------------------------------------------------------------
    # decay_records
    # ------------------------------------------------------------------
    op.create_table(
        "decay_records",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("memory_id", sa.String(26), nullable=False),
        sa.Column("agent_id", sa.String(26), nullable=False),
        sa.Column("decay_policy", sa.String(32), nullable=False),
        sa.Column("score_before", sa.Float, nullable=False),
        sa.Column("score_after", sa.Float, nullable=False),
        sa.Column("decayed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("ix_decay_records_memory_id", "decay_records", ["memory_id"])
    op.create_index("ix_decay_records_decayed_at", "decay_records", ["decayed_at"])


def downgrade() -> None:
    """Drop all initial tables."""
    op.drop_table("decay_records")
    op.drop_table("agent_profiles")
    op.drop_table("contradiction_records")
    op.drop_table("extracted_preferences")
    op.drop_table("reflection_results")
    op.drop_table("reflection_jobs")
    op.drop_table("memory_records")
