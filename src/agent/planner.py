"""Agentic planner: route commands through the unified Mac agent."""

import time

from src.shared.events import AgentCommand
from src.shared.timing import elapsed_ms


async def execute_command(command: AgentCommand) -> str:
    """Run a single command through the Mac agent."""
    started_at = time.perf_counter()
    from src.agent.mac_agent import execute_command_with_mac_agent

    print(f"[planner] routing to mac agent for goal={command.text!r}")
    result = await execute_command_with_mac_agent(command)
    print("[timing] planner mac-agent path took {:.1f}ms".format(elapsed_ms(started_at)))
    return result
