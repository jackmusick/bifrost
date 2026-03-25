"""
Batch Analysis Workflows for HaloPSA Reports

Data provider for report group listing and batch workflow for analyzing/seeding
all built-in HaloPSA reports into the knowledge base.
"""

from __future__ import annotations

import logging

from bifrost import data_provider, knowledge, workflow
from modules.extensions.halopsa import execute_sql
from features.halopsa_reporting.services.analysis import (
    analyze_and_seed,
    NS_REPORTS,
    NS_RULES,
)

logger = logging.getLogger(__name__)


@data_provider(
    name="List HaloPSA Report Groups",
    description="Returns HaloPSA report groups with report counts for use in form dropdowns.",
)
async def list_report_groups() -> list[dict]:
    """
    Query AnalyzerProfile joined to LOOKUP to get distinct report groups
    with their report counts. Returns [{label, value}, ...] for multiselect.
    """
    rows = await execute_sql(
        "SELECT L.fvalue [Group], COUNT(*) [Count] "
        "FROM AnalyzerProfile AP "
        "JOIN LOOKUP L ON (AP.APGroupID + 1) = L.fcode AND L.fid = 41 "
        "GROUP BY L.fvalue"
    )
    results = [
        {"label": f"{row['Group']} ({row['Count']})", "value": row["Group"]}
        for row in rows
    ]
    return sorted(results, key=lambda r: r["label"])


@workflow(name="Batch Analyze HaloPSA Reports")
async def batch_analyze_reports(
    skip_existing: bool = True,
    limit: int = 0,
    clear_before_seed: bool = False,
) -> dict:
    """
    Analyze every HaloPSA report and seed the knowledge base.
    Reports whose SQL fails to execute or returns no rows are skipped automatically.

    Args:
        skip_existing: Skip reports already in the knowledge base.
        limit: Cap the number of reports to process (0 = no limit).
        clear_before_seed: Clear knowledge namespaces before seeding.
    """

    # --- Clear phase ---
    cleared = []
    if clear_before_seed:
        for ns in (NS_REPORTS, NS_RULES):
            await knowledge.delete_namespace(namespace=ns)
            cleared.append(ns)
            logger.info(f"Cleared knowledge namespace: {ns}")

    # --- Fetch all reports ---
    rows = await execute_sql(
        "SELECT AP.APid [Id], L.fvalue [Group], AP.APTitle [Name] "
        "FROM AnalyzerProfile AP "
        "JOIN LOOKUP L ON (AP.APGroupID + 1) = L.fcode AND L.fid = 41"
    )
    rows.sort(key=lambda r: (r.get("Group", ""), r.get("Name", "")))
    logger.info(f"Found {len(rows)} total reports")

    # --- Skip existing ---
    if skip_existing:
        existing_keys = set()
        for row in rows:
            report_key = f"report-{row['Id']}"
            results = await knowledge.search(
                query=report_key, namespace=[NS_REPORTS], limit=1
            )
            if any(r.key == report_key for r in results):
                existing_keys.add(row["Id"])
        before = len(rows)
        rows = [r for r in rows if r["Id"] not in existing_keys]
        logger.info(f"Skipping {before - len(rows)} existing, {len(rows)} remaining")

    # --- Apply limit ---
    if limit > 0:
        rows = rows[:limit]

    # --- Process reports ---
    successes = []
    skipped = []
    failures = []
    for row in rows:
        report_id = row["Id"]
        try:
            result = await analyze_and_seed(report_id)
            successes.append(
                {"id": report_id, "name": row["Name"], "group": row["Group"], **result}
            )
            logger.info(f"Seeded report {report_id}: {row['Name']}")
        except ValueError as e:
            # SQL validation failures, missing SQL, etc. — expected skips
            skipped.append(
                {"id": report_id, "name": row["Name"], "group": row["Group"], "reason": str(e)}
            )
        except Exception as e:
            failures.append(
                {"id": report_id, "name": row["Name"], "group": row["Group"], "error": repr(e)}
            )
            logger.warning(f"Failed to seed report {report_id} ({row['Name']}): {e!r}")

    return {
        "total_found": len(successes) + len(skipped) + len(failures),
        "succeeded": len(successes),
        "skipped": len(skipped),
        "failed": len(failures),
        "cleared_namespaces": cleared,
        "successes": successes,
        "skipped_reports": skipped,
        "failures": failures,
    }
