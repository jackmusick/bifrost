"""AgentRunResponse + AgentRunDetailResponse include new fields."""
from src.models.contracts.agent_runs import AgentRunResponse, AgentRunDetailResponse


def test_agent_run_response_has_new_fields():
    fields = AgentRunResponse.model_fields
    for name in (
        "asked", "did", "metadata", "confidence", "confidence_reason",
        "verdict", "verdict_note", "verdict_set_at", "verdict_set_by",
    ):
        assert name in fields, f"missing {name} on AgentRunResponse"


def test_agent_run_detail_response_inherits_new_fields():
    fields = AgentRunDetailResponse.model_fields
    for name in (
        "asked", "did", "metadata", "confidence",
        "verdict", "verdict_note",
    ):
        assert name in fields
