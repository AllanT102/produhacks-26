"""Agent loop: consumes finalized transcripts and runs the agentic planner."""

import asyncio
import time
from typing import Awaitable, Callable, Optional

from src.agent.controller import AgentController
from src.agent.planner import execute_command
from src.shared.events import AgentCommand

StatusCallback = Callable[[str, str], Awaitable[None]]
_MIN_PROCESSING_VISIBLE_SECONDS = 0.55


async def _emit_status(callback: Optional[StatusCallback], state: str, detail: str) -> None:
    """Send agent status updates to interested observers."""
    if callback is not None:
        await callback(state, detail)


async def _emit_ready_when_visible(
    callback: Optional[StatusCallback],
    started_at: float,
) -> None:
    """Keep the processing state on screen long enough to be perceptible."""
    remaining = _MIN_PROCESSING_VISIBLE_SECONDS - (time.perf_counter() - started_at)
    if remaining > 0:
        await asyncio.sleep(remaining)
    await _emit_status(callback, "idle", "Ready")


async def run_agent_loop(
    agent_queue: "asyncio.Queue[AgentCommand]",
    controller: AgentController,
    on_status: Optional[StatusCallback] = None,
) -> None:
    """Consume finalized transcript commands and run the planner with status updates.

    Commands that arrive while the agent is busy stay queued and run next.
    """
    while True:
        command = await agent_queue.get()
        try:
            controller.reset()
            await _emit_status(on_status, "processing", command.text)
            print(f"[agent] received transcript_id={command.transcript_id} text={command.text!r}")
            started_at = time.perf_counter()
            task = asyncio.create_task(execute_command(command))
            controller.set_current_task(task)
            summary = await task
            print("[timing] command total took {:.1f}ms".format((time.perf_counter() - started_at) * 1000.0))
            print(f"[agent] result={summary}")
            await _emit_ready_when_visible(on_status, started_at)
        except asyncio.CancelledError:
            print("[agent] stopped")
            await _emit_status(on_status, "stopped", "Stopped")
        except Exception as exc:
            print(f"[agent] error executing command: {exc}")
            await _emit_status(on_status, "error", str(exc))
        finally:
            controller.set_current_task(None)
            agent_queue.task_done()
