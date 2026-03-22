"""Agentic planner: route commands through the unified Mac agent."""

import time
from typing import Awaitable, Callable, Optional

from src.agent.read_aloud import maybe_execute_read_aloud
from src.shared.events import AgentCommand
from src.shared.timing import elapsed_ms

StatusCallback = Callable[[str, str], Awaitable[None]]


async def execute_command(
    command: AgentCommand,
    on_status: Optional[StatusCallback] = None,
) -> str:
    """Run a single command through the Mac agent."""
    started_at = time.perf_counter()
    readback_summary = await maybe_execute_read_aloud(command.text, on_status=on_status)
    if readback_summary is not None:
        print(
            "[timing] planner read-aloud path took {:.1f}ms".format(
                elapsed_ms(started_at)
            )
        )
        return readback_summary

    from src.agent.mac_agent import execute_command_with_mac_agent

    print(f"[planner] routing to mac agent for goal={command.text!r}")
    result = await execute_command_with_mac_agent(command)
    print(
        "[timing] planner mac-agent path took {:.1f}ms".format(elapsed_ms(started_at))
    )
    return result
