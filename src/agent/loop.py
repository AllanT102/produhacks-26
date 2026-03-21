"""Agent loop: consumes finalized transcripts and runs the agentic planner."""

import asyncio
import os

from src.agent.planner import execute_command
from src.agent.providers import make_provider
from src.shared.events import AgentCommand


def _build_provider():
    return make_provider(
        provider=os.environ.get("AGENT_PROVIDER", "anthropic"),
        model=os.environ.get("AGENT_MODEL") or None,
    )


async def run_agent_loop(agent_queue: "asyncio.Queue[AgentCommand]") -> None:
    """Consume finalized transcript commands one at a time and execute them.

    The LLM provider is selected once at startup via AGENT_PROVIDER and
    AGENT_MODEL env vars (defaults to Anthropic claude-opus-4-6).
    """
    provider = _build_provider()
    print(f"[agent] provider={type(provider).__name__}")

    while True:
        command = await agent_queue.get()
        try:
            print(f"[agent] received transcript_id={command.transcript_id} text={command.text!r}")
            result = await execute_command(command, provider=provider)
            print(f"[agent] result={result!r}")
        except Exception as exc:
            print(f"[agent] error executing command: {exc}")
        finally:
            agent_queue.task_done()
