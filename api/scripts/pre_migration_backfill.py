"""
Pre-migration data backfill for workspace redesign.

Runs BEFORE alembic migrations to preserve data from tables that will be
dropped (workspace_files, workflows.code). Writes content into file_index
DB + S3 via FileIndexService so it survives the destructive migrations.

Also generates missing form/agent YAML files and .bifrost/ manifests.

Defensive: checks whether old tables still exist before reading, and
whether file_index exists before writing. Safe no-op on already-migrated DBs.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)


async def _table_exists(db: AsyncSession, table_name: str) -> bool:
    """Check if a table exists via information_schema."""
    result = await db.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :name"
        ),
        {"name": table_name},
    )
    return result.scalar_one_or_none() is not None


async def _column_exists(db: AsyncSession, table_name: str, column_name: str) -> bool:
    """Check if a column exists on a table via information_schema."""
    result = await db.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' "
            "AND table_name = :table AND column_name = :col"
        ),
        {"table": table_name, "col": column_name},
    )
    return result.scalar_one_or_none() is not None


async def backfill_workspace_data(db: AsyncSession) -> dict[str, int]:
    """
    Backfill data from old tables into file_index + S3.

    Returns stats dict with counts of migrated items.
    """
    from sqlalchemy import select as sa_select

    from src.services.file_index_service import FileIndexService
    from src.services.repo_storage import RepoStorage
    from src.services.repo_sync_writer import RepoSyncWriter

    stats = {
        "workspace_files": 0,
        "workflow_code": 0,
        "forms": 0,
        "agents": 0,
        "manifest": 0,
    }

    # ---------------------------------------------------------------
    # Step 0: Check if file_index table exists (target for writes)
    # ---------------------------------------------------------------
    has_file_index = await _table_exists(db, "file_index")
    if not has_file_index:
        logger.info(
            "file_index table does not exist yet — skipping backfill. "
            "Alembic will create it and the reconciler will handle the rest."
        )
        return stats

    # Check what old data sources are available
    has_workspace_files = await _table_exists(db, "workspace_files")
    has_workflow_code = await _column_exists(db, "workflows", "code")

    if not has_workspace_files and not has_workflow_code:
        logger.info(
            "No old tables to migrate (workspace_files table gone, "
            "workflows.code column gone) — nothing to backfill."
        )
        # Still generate form/agent YAML and manifests below
    else:
        logger.info(
            f"Found old data sources: workspace_files={has_workspace_files}, "
            f"workflows.code={has_workflow_code}"
        )

    repo_storage = RepoStorage()
    file_index_svc = FileIndexService(db, repo_storage)

    # ---------------------------------------------------------------
    # Step 1: Migrate workspace_files content
    # ---------------------------------------------------------------
    if has_workspace_files:
        try:
            result = await db.execute(
                text(
                    "SELECT path, content FROM workspace_files "
                    "WHERE content IS NOT NULL "
                    "AND (is_deleted = false OR is_deleted IS NULL)"
                )
            )
            rows = result.all()
            for row in rows:
                path, content = row[0], row[1]
                try:
                    # Check if already exists in file_index
                    existing = await file_index_svc.read(path)
                    if existing is not None:
                        continue
                    await file_index_svc.write(path, content.encode("utf-8"))
                    stats["workspace_files"] += 1
                except Exception as e:
                    logger.warning(f"Failed to migrate workspace_file {path}: {e}")
            logger.info(f"Migrated {stats['workspace_files']} workspace_files entries")
        except Exception as e:
            logger.warning(f"Failed to read workspace_files: {e}")

    # ---------------------------------------------------------------
    # Step 2: Migrate workflows.code
    # ---------------------------------------------------------------
    if has_workflow_code:
        try:
            result = await db.execute(
                text(
                    "SELECT path, code FROM workflows "
                    "WHERE code IS NOT NULL "
                    "AND path IS NOT NULL "
                    "AND is_active = true"
                )
            )
            rows = result.all()
            for row in rows:
                path, code = row[0], row[1]
                try:
                    # workspace_files content takes precedence (already written above)
                    existing = await file_index_svc.read(path)
                    if existing is not None:
                        continue
                    await file_index_svc.write(path, code.encode("utf-8"))
                    stats["workflow_code"] += 1
                except Exception as e:
                    logger.warning(f"Failed to migrate workflow code {path}: {e}")
            logger.info(f"Migrated {stats['workflow_code']} workflow code entries")
        except Exception as e:
            logger.warning(f"Failed to read workflows.code: {e}")

    # ---------------------------------------------------------------
    # Step 3: Generate missing form YAML files
    # ---------------------------------------------------------------
    try:
        from src.models.orm.forms import Form
        from src.services.file_storage.indexers.form import _serialize_form_to_yaml

        form_result = await db.execute(
            sa_select(Form)
            .where(Form.is_active == True)  # noqa: E712
            .options(selectinload(Form.fields))
        )
        forms = form_result.scalars().all()

        for form in forms:
            try:
                form_path = f"forms/{form.id}.form.yaml"
                existing = await file_index_svc.read(form_path)
                if existing is not None:
                    continue
                yaml_bytes = _serialize_form_to_yaml(form)
                await file_index_svc.write(form_path, yaml_bytes)
                stats["forms"] += 1
            except Exception as e:
                logger.warning(f"Failed to serialize form {form.name}: {e}")

        logger.info(f"Generated {stats['forms']} form YAML files")
    except Exception as e:
        logger.warning(f"Failed to generate form YAML files: {e}")

    # ---------------------------------------------------------------
    # Step 4: Generate missing agent YAML files
    # ---------------------------------------------------------------
    try:
        from src.models.orm.agents import Agent
        from src.services.file_storage.indexers.agent import _serialize_agent_to_yaml

        agent_result = await db.execute(
            sa_select(Agent)
            .where(Agent.is_active == True)  # noqa: E712
            .where(Agent.is_system == False)  # noqa: E712
            .options(
                selectinload(Agent.tools),
                selectinload(Agent.delegated_agents),
                selectinload(Agent.roles),
            )
        )
        agents = agent_result.scalars().unique().all()

        for agent in agents:
            try:
                agent_path = f"agents/{agent.id}.agent.yaml"
                existing = await file_index_svc.read(agent_path)
                if existing is not None:
                    continue
                yaml_bytes = _serialize_agent_to_yaml(agent)
                await file_index_svc.write(agent_path, yaml_bytes)
                stats["agents"] += 1
            except Exception as e:
                logger.warning(f"Failed to serialize agent {agent.name}: {e}")

        logger.info(f"Generated {stats['agents']} agent YAML files")
    except Exception as e:
        logger.warning(f"Failed to generate agent YAML files: {e}")

    # ---------------------------------------------------------------
    # Step 5: Generate .bifrost/ manifest
    # ---------------------------------------------------------------
    try:
        writer = RepoSyncWriter(db)
        await writer.regenerate_manifest()
        stats["manifest"] = 1
        logger.info("Generated .bifrost/ manifest files")
    except Exception as e:
        logger.warning(f"Failed to generate manifest: {e}")

    # Commit all writes
    await db.commit()

    logger.info(
        f"Backfill complete: {stats['workspace_files']} workspace_files, "
        f"{stats['workflow_code']} workflow code, {stats['forms']} forms, "
        f"{stats['agents']} agents, manifest={'yes' if stats['manifest'] else 'no'}"
    )

    return stats
