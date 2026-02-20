"""backfill integration config types and encrypt secrets

Revision ID: 20260219_backfill_config_types
Revises: 20260218_oauth_audience
Create Date: 2026-02-19
"""

from alembic import op
import sqlalchemy as sa

revision = "20260219_backfill_config_types"
down_revision = "20260218_oauth_audience"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Backfill config_type from integration schema and encrypt secret values."""
    from src.core.security import encrypt_secret

    conn = op.get_bind()

    # Find all configs with integration_id that need backfill
    rows = conn.execute(sa.text("""
        SELECT c.id, c.key, c.value, c.config_type, ics.type as schema_type
        FROM configs c
        JOIN integration_config_schema ics
          ON ics.integration_id = c.integration_id AND ics.key = c.key
        WHERE c.integration_id IS NOT NULL
    """)).fetchall()

    for row in rows:
        config_id = row.id
        current_type = row.config_type
        schema_type = row.schema_type
        value = row.value

        # Skip if config_type already matches schema
        if current_type == schema_type:
            continue

        # For secrets, encrypt the plaintext value
        if schema_type == "secret":
            raw = value.get("value") if isinstance(value, dict) else value
            if isinstance(raw, str) and not raw.startswith("gAAA"):
                # Encrypt and update both config_type and value
                encrypted = encrypt_secret(raw)
                conn.execute(
                    sa.text(
                        "UPDATE configs SET config_type = :schema_type, "
                        "value = jsonb_build_object('value', CAST(:enc_val AS text)) "
                        "WHERE id = :config_id"
                    ),
                    {
                        "schema_type": schema_type,
                        "enc_val": encrypted,
                        "config_id": config_id,
                    },
                )
            else:
                # Just update config_type
                conn.execute(
                    sa.text(
                        "UPDATE configs SET config_type = :schema_type WHERE id = :config_id"
                    ),
                    {"schema_type": schema_type, "config_id": config_id},
                )
        else:
            # Non-secret: just update config_type
            conn.execute(
                sa.text(
                    "UPDATE configs SET config_type = :schema_type WHERE id = :config_id"
                ),
                {"schema_type": schema_type, "config_id": config_id},
            )


def downgrade() -> None:
    """No downgrade - encryption is one-way for security."""
    pass
