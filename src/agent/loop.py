"""Agent loop: consumes finalized transcripts and runs the agentic planner."""

import asyncio

from src.agent.planner import execute_command
from src.shared.events import AgentCommand

async def run_agent_loop(agent_queue: "asyncio.Queue[AgentCommand]") -> None:
    """Consume finalized transcript commands one at a time and execute them.

    Any commands that arrive while the agent is busy are drained and discarded
    so the same utterance can't trigger multiple back-to-back executions.
    """
    while True:
        command = await agent_queue.get()
        try:
            print(f"[agent] received transcript_id={command.transcript_id} text={command.text!r}")
            result = await execute_command(command)
            print(f"[agent] result={result!r}")
        except Exception as exc:
            print(f"[agent] error executing command: {exc}")
        finally:
            agent_queue.task_done()
            # Drain any commands that queued up while we were busy.
            drained = 0
            while not agent_queue.empty():
                agent_queue.get_nowait()
                agent_queue.task_done()
                drained += 1
            if drained:
                print(f"[agent] discarded {drained} command(s) that arrived during execution")
