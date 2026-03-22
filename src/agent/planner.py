"""Agentic planner: route commands through the warm browser-use backend."""

import time
from typing import Awaitable, Callable, Optional

from src.agent.read_aloud import maybe_execute_read_aloud
from src.shared.events import AgentCommand
from src.shared.timing import elapsed_ms

StatusCallback = Callable[[str, str], Awaitable[None]]


def _load_browser_use_backend():
    """Import browser-use lazily so normal startup stays fast."""
    from src.agent.browser_use_backend import execute_command_with_browser_use, should_use_browser_use

    return execute_command_with_browser_use, should_use_browser_use


async def execute_command(
    command: AgentCommand,
    on_status: Optional[StatusCallback] = None,
) -> str:
    """Run a single command through the persistent browser-use backend."""
    started_at = time.perf_counter()
    readback_summary = await maybe_execute_read_aloud(command.text, on_status=on_status)
    if readback_summary is not None:
        print("[timing] planner read-aloud path took {:.1f}ms".format(elapsed_ms(started_at)))
        return readback_summary

    execute_command_with_browser_use, should_use_browser_use = _load_browser_use_backend()

    if not should_use_browser_use(command):
        return "browser-use is unavailable. Ensure BROWSER_USE_ENABLED=1 and .venv-browseruse is set up."

    print(f"[planner] routing to browser-use backend for goal={command.text!r}")
    result = await execute_command_with_browser_use(command)
    print("[timing] planner browser-use path took {:.1f}ms".format(elapsed_ms(started_at)))
    return result
