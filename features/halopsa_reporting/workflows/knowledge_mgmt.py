"""
HaloPSA Knowledge Tools

Agent-facing tools for searching and saving HaloPSA knowledge.
The storage logic lives in features.halopsa_reporting.services.analysis.
"""

from bifrost import tool, knowledge, UserError
from features.halopsa_reporting.services.analysis import NS_REPORTS, NS_RULES
import logging

logger = logging.getLogger(__name__)


@tool(description="Save a working HaloPSA SQL report to knowledge for future reuse.")
async def save_halopsa_report(
    name: str,
    description: str,
    sql: str,
    tables_used: str = "",
    group: str = "",
) -> dict:
    key = f"report-user-{name.lower().replace(' ', '-')[:60]}"
    content = (
        f"Report: {name}\n"
        f"Group: {group}\n"
        f"Source: agent\n"
        f"Description: {description}\n"
        f"Tables: {tables_used}\n\n"
        f"SQL:\n{sql}"
    )
    stored_key = await knowledge.store(
        content=content, namespace=NS_REPORTS, key=key,
        metadata={"name": name, "group": group, "source": "agent", "tables": tables_used, "type": "report"},
    )
    logger.info(f"Saved report '{name}' to {NS_REPORTS}")
    return {"key": stored_key, "namespace": NS_REPORTS, "name": name}


@tool(description="Save a HaloPSA schema rule or pattern to knowledge for future SQL generation.")
async def save_halopsa_rule(
    rule: str, category: str = "general", evidence: str = "",
    confidence: str = "high", source_report: str = "",
) -> dict:
    rule_slug = rule.lower().replace(" ", "-")[:80]
    key = f"rule-{category.lower().replace(' ', '-')}-{rule_slug}"
    content = (
        f"Rule: {rule}\nCategory: {category}\nConfidence: {confidence}\n"
        f"Source: {source_report}\nEvidence: {evidence}"
    )
    stored_key = await knowledge.store(
        content=content, namespace=NS_RULES, key=key,
        metadata={"category": category, "confidence": confidence, "type": "rule", "source_report": source_report},
    )
    logger.info(f"Saved rule to {NS_RULES}")
    return {"key": stored_key, "namespace": NS_RULES, "category": category}


@tool(description="Search HaloPSA knowledge base for relevant reports and schema rules.")
async def search_halopsa_knowledge(
    query: str, search_reports: bool = True, search_rules: bool = True, limit: int = 5,
) -> dict:
    results = {"reports": [], "rules": [], "query": query}
    namespaces = []
    if search_reports: namespaces.append(NS_REPORTS)
    if search_rules: namespaces.append(NS_RULES)
    if not namespaces: raise UserError("Must search at least one namespace.")
    docs = await knowledge.search(query=query, namespace=namespaces, limit=limit)
    for doc in docs:
        entry = {"key": doc.key, "content": doc.content, "score": doc.score, "metadata": doc.metadata}
        if doc.namespace == NS_REPORTS: results["reports"].append(entry)
        elif doc.namespace == NS_RULES: results["rules"].append(entry)
    results["total_found"] = len(results["reports"]) + len(results["rules"])
    return results
