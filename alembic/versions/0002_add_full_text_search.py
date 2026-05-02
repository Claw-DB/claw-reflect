"""Add PostgreSQL GIN full-text search index on memory_records.content using pg_trgm.

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-01 00:01:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Enable pg_trgm extension and create GIN trigram index on memory content."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_memory_content_trgm "
        "ON memory_records USING GIN (content gin_trgm_ops)"
    )


def downgrade() -> None:
    """Remove the trigram index (extension is left in place to avoid side effects)."""
    op.execute("DROP INDEX IF EXISTS idx_memory_content_trgm")
