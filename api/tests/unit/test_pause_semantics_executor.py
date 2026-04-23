"""Pause check at executor entry.

Verifies the autonomous agent executor short-circuits when the agent is paused
(``is_active=False``) and that the check happens *before* the main execution
loop, so in-flight runs are not killed mid-iteration.
"""
from __future__ import annotations

import inspect

from src.services.execution.autonomous_agent_executor import AutonomousAgentExecutor


def test_run_method_has_pause_check_before_loop():
    """The pause check must live before the main execution loop, not inside it.

    This is a structural assertion — paired with the e2e test that proves the
    HTTP-level behavior — to guard against future refactors that move the
    check into the loop body (which would kill in-flight work).
    """
    source = inspect.getsource(AutonomousAgentExecutor.run)
    pause_pos = source.find("if not agent.is_active")
    loop_pos = source.find("while iterations_used")

    assert pause_pos > 0, "No pause check (`if not agent.is_active`) found in run()"
    assert loop_pos > 0, "Could not locate `while iterations_used` loop in run()"
    assert pause_pos < loop_pos, (
        "Pause check must occur BEFORE the main execution loop so in-flight "
        "runs complete normally when an agent is paused mid-run."
    )


def test_run_method_returns_paused_status_dict_shape():
    """The pause short-circuit must return a dict with ``status='paused'`` and
    ``accepted=False`` so /execute can return it directly to clients."""
    source = inspect.getsource(AutonomousAgentExecutor.run)
    pause_section = source[source.find("if not agent.is_active"):]
    # Find end of the pause-handling block (next blank line or `step_number = 0`)
    pause_section = pause_section.split("step_number = 0")[0]

    assert '"status": "paused"' in pause_section, "Paused branch must set status='paused'"
    assert '"accepted": False' in pause_section, "Paused branch must set accepted=False"
    assert '"message"' in pause_section, "Paused branch must include a message"
