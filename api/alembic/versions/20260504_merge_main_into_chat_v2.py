"""Merge main (post-MCP-client) into chat-v2 (M2 backend)

Revision ID: 20260504_merge_main_chat_v2
Revises: 20260503_agent_mcp_grants, 20260428_chat_v2_m2
Create Date: 2026-05-04

Merges the two divergent heads created when feature/chat-v2 was rebased
behind main. Main now ends at 20260503_agent_mcp_grants (downstream of
20260504_backfill_table_access and 20260502_external_mcp from #177).
Chat-v2 ends at 20260428_chat_v2_m2. No schema changes — both branches'
migrations stand on their own; this revision exists solely to give
Alembic a single head.
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "20260504_merge_main_chat_v2"
down_revision: tuple[str, str] = (
    "20260503_agent_mcp_grants",
    "20260428_chat_v2_m2",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
