"""Claude-powered agentic loop: transcript → tool calls → desktop actions."""

import asyncio
import json
import os
from typing import Optional

import anthropic

from src.shared.events import AgentCommand, ToolCall
from src.tool_runtime.runtime import execute_tool
from src.tool_runtime.schemas import TOOLS

_MODEL = "claude-opus-4-6"
_MAX_ITERATIONS = 20


def _make_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    return anthropic.Anthropic(api_key=api_key)


async def execute_command(command: AgentCommand, max_iterations: int = _MAX_ITERATIONS) -> str:
    """Run the agentic loop for a single voice command.

    Sends the user's intent to Claude along with all desktop tools, then
    iterates screenshot → reasoning → tool execution until Claude calls
    task_complete or the iteration limit is reached.

    Returns a human-readable summary of what was accomplished.
    """
    client = _make_client()
    messages = [{"role": "user", "content": command.text}]

    print(f"[planner] goal={command.text!r}")

    for iteration in range(max_iterations):
        print(f"[planner] iteration={iteration + 1}/{max_iterations}")

        response = await asyncio.to_thread(
            client.messages.create,
            model=_MODEL,
            max_tokens=4096,
            tools=TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return "Done."

        if response.stop_reason != "tool_use":
            return f"Stopped unexpectedly: {response.stop_reason}"

        tool_results = []
        finished = False
        summary = ""

        for block in response.content:
            if block.type != "tool_use":
                continue

            name: str = block.name
            inputs: dict = block.input
            print(f"[planner] tool={name} inputs={inputs}")

            if name == "task_complete":
                summary = inputs.get("summary", "Task complete.")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": summary,
                })
                finished = True
                continue

            result = await asyncio.to_thread(
                execute_tool, ToolCall(tool=name, args=inputs)
            )

            if name == "screenshot" and result.ok and result.result:
                # Return screenshot as a vision image block, not raw JSON.
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": result.result["media_type"],
                                "data": result.result["data"],
                            },
                        }
                    ],
                })
            else:
                payload = result.result if result.ok else result.error
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(payload),
                })

        messages.append({"role": "user", "content": tool_results})

        if finished:
            print(f"[planner] done — {summary}")
            return summary

    return f"Reached {max_iterations} iterations without completing the task."


# ---------------------------------------------------------------------------
# Legacy synchronous shim kept for any callers that import the old interface.
# ---------------------------------------------------------------------------

def plan_from_transcript(text: str) -> dict:
    """Deprecated: returns a stub plan. Use execute_command() instead."""
    return {
        "goal": text.strip(),
        "steps": [{"type": "reason", "status": "pending"}],
    }
