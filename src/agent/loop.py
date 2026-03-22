"""Agent loop: consumes finalized transcripts and runs the agentic planner."""

import asyncio
from typing import Awaitable, Callable, Optional

from src.agent.controller import AgentController
from src.agent.planner import execute_command
from src.shared.events import AgentCommand

StatusCallback = Callable[[str, str], Awaitable[None]]


async def _emit_status(callback: Optional[StatusCallback], state: str, detail: str) -> None:
    """Send agent status updates to interested observers."""
    if callback is not None:
        await callback(state, detail)


async def run_agent_loop(
    agent_queue: "asyncio.Queue[AgentCommand]",
    controller: AgentController,
    on_status: Optional[StatusCallback] = None,
    on_step: Optional[Callable[[str], None]] = None,
) -> None:
    """Consume finalized transcript commands and run the planner with status updates."""
    while True:
        command = await agent_queue.get()
        try:
            controller.reset()
            await _emit_status(on_status, "processing", command.text)
            print(f"[agent] received transcript_id={command.transcript_id} text={command.text!r}")
            task = asyncio.create_task(execute_command(command, on_step=on_step))
            controller.set_current_task(task)
            summary = await task
            print(f"[agent] result={summary}")
            await _emit_status(on_status, "done", summary)
        except asyncio.CancelledError:
            print("[agent] stopped")
            await _emit_status(on_status, "stopped", "Stopped")
        except Exception as exc:
            print(f"[agent] error executing command: {exc}")
            await _emit_status(on_status, "error", str(exc))
        finally:
            controller.set_current_task(None)
            agent_queue.task_done()
            drained = 0
            while not agent_queue.empty():
                agent_queue.get_nowait()
                agent_queue.task_done()
                drained += 1
            if drained:
                print(f"[agent] discarded {drained} command(s) that arrived during execution")
