"""Fix global metrics duplicates

Revision ID: fix_global_metrics_duplicates
Revises: add_log_sequence
Create Date: 2025-12-06

Fixes issue where multiple rows with organization_id IS NULL could exist
for the same date, causing MultipleResultsFound errors.

1. Deduplicates existing global (org_id IS NULL) rows by aggregating them
2. Adds a partial unique index to enforce single global row per date
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "fix_global_metrics_duplicates"
down_revision = "add_log_sequence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Deduplicate existing global metrics rows (organization_id IS NULL)
    # For each date with duplicates, aggregate into a single row
    op.execute("""
        WITH duplicates AS (
            SELECT date
            FROM execution_metrics_daily
            WHERE organization_id IS NULL
            GROUP BY date
            HAVING COUNT(*) > 1
        ),
        aggregated AS (
            SELECT
                d.date,
                SUM(m.execution_count) as execution_count,
                SUM(m.success_count) as success_count,
                SUM(m.failed_count) as failed_count,
                SUM(m.timeout_count) as timeout_count,
                SUM(m.cancelled_count) as cancelled_count,
                SUM(m.total_duration_ms) as total_duration_ms,
                MAX(m.max_duration_ms) as max_duration_ms,
                SUM(m.total_memory_bytes) as total_memory_bytes,
                MAX(m.peak_memory_bytes) as peak_memory_bytes,
                SUM(m.total_cpu_seconds) as total_cpu_seconds,
                MAX(m.peak_cpu_seconds) as peak_cpu_seconds,
                MIN(m.created_at) as created_at
            FROM duplicates d
            JOIN execution_metrics_daily m ON m.date = d.date AND m.organization_id IS NULL
            GROUP BY d.date
        ),
        to_keep AS (
            -- For each duplicate date, keep the row with the lowest id
            SELECT DISTINCT ON (date) id, date
            FROM execution_metrics_daily
            WHERE organization_id IS NULL
              AND date IN (SELECT date FROM duplicates)
            ORDER BY date, id
        )
        -- Update the kept row with aggregated values
        UPDATE execution_metrics_daily m
        SET
            execution_count = a.execution_count,
            success_count = a.success_count,
            failed_count = a.failed_count,
            timeout_count = a.timeout_count,
            cancelled_count = a.cancelled_count,
            total_duration_ms = a.total_duration_ms,
            avg_duration_ms = CASE
                WHEN a.execution_count > 0
                THEN a.total_duration_ms / a.execution_count
                ELSE 0
            END,
            max_duration_ms = a.max_duration_ms,
            total_memory_bytes = a.total_memory_bytes,
            peak_memory_bytes = a.peak_memory_bytes,
            total_cpu_seconds = a.total_cpu_seconds,
            peak_cpu_seconds = a.peak_cpu_seconds,
            created_at = a.created_at,
            updated_at = NOW()
        FROM aggregated a, to_keep k
        WHERE m.id = k.id AND m.date = a.date
    """)

    # Step 2: Delete the duplicate rows (keep only the one we updated)
    op.execute("""
        WITH to_keep AS (
            SELECT DISTINCT ON (date) id
            FROM execution_metrics_daily
            WHERE organization_id IS NULL
            ORDER BY date, id
        )
        DELETE FROM execution_metrics_daily
        WHERE organization_id IS NULL
          AND id NOT IN (SELECT id FROM to_keep)
    """)

    # Step 3: Create partial unique index for global metrics (org_id IS NULL)
    # This prevents future duplicates
    op.create_index(
        "uq_metrics_daily_date_global",
        "execution_metrics_daily",
        ["date"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_metrics_daily_date_global", table_name="execution_metrics_daily")
