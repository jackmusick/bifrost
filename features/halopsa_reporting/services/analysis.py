"""
Report Analysis Service

Core logic for analyzing HaloPSA reports with AI and storing results to knowledge.
Used by both the single-report workflow and the batch runner.
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel
from bifrost import ai, knowledge
from modules.extensions.halopsa import execute_sql

logger = logging.getLogger(__name__)

NS_REPORTS = "halopsa-reports"
NS_RULES = "halopsa-schema-rules"

# --- Structured output models ---

class SchemaRule(BaseModel):
    category: str
    rule: str
    evidence: Optional[str] = None
    confidence: str = "high"


class ReportAnalysis(BaseModel):
    report_id: int
    report_name: str
    report_group: str
    summary: str
    tables_used: list[str] = []
    rules: list[SchemaRule] = []


ANALYSIS_SYSTEM_PROMPT = """You are a database schema analyst specializing in HaloPSA's SQL Server database.

Analyze a SQL report query and extract facts for a knowledge base that helps an AI agent write correct SQL.

RULES:
1. Only extract facts DIRECTLY OBSERVABLE in the SQL — no generalizing from one example.
2. Note column naming patterns, standard WHERE filters (fdeleted = 0, etc.), data type hints
   (FORMAT 'C2' = currency, / 60.0 = minutes), and gotchas (backwards booleans, unusual names).
3. Confidence: "high" = directly visible, "medium" = reasonable inference, "low" = guess to verify.

OUTPUT:
- summary: What the report does and which business questions it answers, for someone building a similar report.
- tables_used: Every table/view referenced in the SQL.
- rules: Schema facts, gotchas, and best practices observed. Each rule needs category, rule text,
  evidence (quote from SQL), and confidence level.
"""


async def fetch_report(report_id: int) -> dict:
    """Pull a report's metadata and SQL from AnalyzerProfile."""
    rows = await execute_sql(
        f"SELECT APid [Id], fvalue [Group], APTitle [Name], CAST(APSQL AS NVARCHAR(MAX)) [SQL] "
        f"FROM AnalyzerProfile "
        f"JOIN LOOKUP ON (APGroupID + 1) = fcode AND fid = 41 "
        f"WHERE APid = {int(report_id)}"
    )
    if not rows:
        return None
    return rows[0]


async def validate_report_sql(report_sql: str, report_name: str, report_id: int) -> bool:
    """Try executing the report SQL. Returns True if it runs and returns rows."""
    try:
        rows = await execute_sql(report_sql)
        if not rows:
            logger.warning(f"Skipping '{report_name}' (ID {report_id}): SQL returned no rows")
            return False
        return True
    except Exception as e:
        logger.warning(f"Skipping '{report_name}' (ID {report_id}): SQL execution failed: {e!r}")
        return False


async def analyze_report(report_id: int) -> tuple[ReportAnalysis, str]:
    """
    Analyze a single HaloPSA report with AI.
    Validates the SQL executes first, then sends to AI for structured analysis.
    Returns (analysis, report_sql) so callers don't need to re-fetch.
    """
    report = await fetch_report(report_id)
    if not report:
        raise ValueError(f"Report ID {report_id} not found in AnalyzerProfile.")

    report_sql = report.get("SQL", "")
    report_name = report.get("Name", "Unknown")
    report_group = report.get("Group", "Unknown")

    if not report_sql or not report_sql.strip():
        raise ValueError(f"Report '{report_name}' (ID {report_id}) has no SQL content.")

    if not await validate_report_sql(report_sql, report_name, report_id):
        raise ValueError(f"Report '{report_name}' (ID {report_id}) has invalid or empty SQL.")

    user_prompt = (
        f"Analyze this HaloPSA SQL report.\n\n"
        f"Report Name: {report_name}\n"
        f"Report Group: {report_group}\n"
        f"Report ID: {report_id}\n\n"
        f"SQL:\n```sql\n{report_sql}\n```"
    )

    analysis = await ai.complete(
        prompt=user_prompt,
        system=ANALYSIS_SYSTEM_PROMPT,
        response_format=ReportAnalysis,
    )
    return analysis, report_sql


async def seed_report(analysis: ReportAnalysis | dict, report_sql: str = "") -> dict:
    """
    Take an analysis result and store the report SQL + rules to knowledge.
    Pass report_sql to avoid a redundant fetch; if omitted, fetches it.
    Returns a summary of what was stored.
    """
    if isinstance(analysis, dict):
        data = analysis
    else:
        data = analysis.model_dump()

    report_id = data.get("report_id", "")
    report_name = data.get("report_name", "Unknown")
    report_group = data.get("report_group", "")
    summary = data.get("summary", "")
    tables = data.get("tables_used", [])

    # Only fetch SQL if not provided
    if not report_sql:
        report = await fetch_report(int(report_id))
        report_sql = report["SQL"] if report else ""

    # Determine source
    is_custom = report_group and not report_group.startswith("\u26d4")
    source = "halo-custom" if is_custom else "halo-builtin"

    # Save report to knowledge
    report_key = f"report-{report_id}"
    content = f"""Report: {report_name}
Group: {report_group}
Source: {source}
Description: {summary}
Tables: {', '.join(tables)}

SQL:
{report_sql}"""

    await knowledge.store(
        content=content,
        namespace=NS_REPORTS,
        key=report_key,
        metadata={
            "name": report_name,
            "group": report_group,
            "source": source,
            "tables": ", ".join(tables),
            "type": "report",
            "report_id": str(report_id),
        },
    )

    # Save each rule
    rules_saved = 0
    for rule_data in data.get("rules", []):
        try:
            rule_text = rule_data.get("rule", "")
            category = rule_data.get("category", "general")
            rule_slug = rule_text.lower().replace(" ", "-")[:80]
            rule_key = f"rule-{category.lower().replace(' ', '-')}-{rule_slug}"

            content = f"""Rule: {rule_text}
Category: {category}
Confidence: {rule_data.get('confidence', 'high')}
Source: {report_name} (ID: {report_id})
Evidence: {rule_data.get('evidence', '')}"""

            await knowledge.store(
                content=content,
                namespace=NS_RULES,
                key=rule_key,
                metadata={
                    "category": category,
                    "confidence": rule_data.get("confidence", "high"),
                    "type": "rule",
                    "source_report": f"{report_name} (ID: {report_id})",
                },
            )
            rules_saved += 1
        except Exception as e:
            logger.warning(f"Failed to save rule from {report_name}: {e}")

    return {
        "report_key": report_key,
        "rules_saved": rules_saved,
        "rules_total": len(data.get("rules", [])),
        "report_name": report_name,
    }


async def analyze_and_seed(report_id: int) -> dict:
    """Full pipeline: analyze a report then seed to knowledge. Returns summary."""
    analysis, report_sql = await analyze_report(report_id)
    return await seed_report(analysis, report_sql=report_sql)
