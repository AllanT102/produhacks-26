"""Agentic planner: routes all commands through browser-use."""

import time

from src.shared.events import AgentCommand
from src.shared.timing import elapsed_ms


def _load_browser_use_backend():
    """Import browser-use lazily so normal startup stays fast."""
    from src.agent.browser_use_backend import execute_command_with_browser_use, should_use_browser_use

    return execute_command_with_browser_use, should_use_browser_use


async def execute_command(command: AgentCommand) -> str:
    """Run the agentic loop for a single voice command using browser-use."""
    started_at = time.perf_counter()
    execute_command_with_browser_use, should_use_browser_use = _load_browser_use_backend()
    if not should_use_browser_use(command):
        return "browser-use is not available. Ensure the .venv-browseruse environment is set up."
    print(f"[planner] routing to browser-use backend for goal={command.text!r}")
    result = await execute_command_with_browser_use(command)
    print("[timing] planner browser-use path took {:.1f}ms".format(elapsed_ms(started_at)))
    return result
