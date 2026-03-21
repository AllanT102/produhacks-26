"""Simple agent loop for consuming finalized transcripts."""

import asyncio
from typing import Optional

from src.agent.planner import plan_from_transcript
from src.shared.events import AgentCommand


async def run_agent_loop(agent_queue: "asyncio.Queue[AgentCommand]") -> None:
    """Consume finalized transcript commands and print placeholder plans."""
    while True:
        command = await agent_queue.get()
        try:
            plan = plan_from_transcript(command.text)
            print("[agent] transcript={}".format(command.text))
            print("[plan] {}".format(plan))
        finally:
            agent_queue.task_done()
