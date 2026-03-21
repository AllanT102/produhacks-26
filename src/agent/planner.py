"""Claude-powered agentic loop: transcript → tool calls → desktop actions."""

import asyncio
import json
import os

import anthropic
import pyautogui

from src.shared.events import AgentCommand, ToolCall
from src.tool_runtime.runtime import execute_tool
from src.tool_runtime.schemas import TOOLS
from src.tool_runtime.tools.screenshot import screenshot

_MODEL = "claude-opus-4-6"
_MAX_ITERATIONS = 20

# Tools that act on the desktop and require a fresh screenshot beforehand.
_ACTION_TOOLS = {"click", "double_click", "scroll", "type_text", "key_press", "move_to", "drag"}


def _make_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def _build_system_prompt() -> str:
    w, h = pyautogui.size()
    return (
        f"You are a macOS desktop automation agent.\n"
        f"Screen resolution: {w}x{h} pixels. All coordinates must be within this bounds.\n"
        f"You will be shown a screenshot of the current screen before every action.\n"
        f"Use the pixel coordinates visible in the screenshot to determine where to click, "
        f"scroll, or type. Never guess coordinates — always ground them in what you see.\n"
        f"When the user's goal is fully achieved, call task_complete."
    )


def _screenshot_image_block() -> dict:
    """Take a live screenshot and return it as an API image content block."""
    result = screenshot()
    if not result["ok"]:
        return {"type": "text", "text": f"[screenshot failed: {result['error']}]"}
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": result["media_type"],
            "data": result["data"],
        },
    }


async def execute_command(command: AgentCommand, max_iterations: int = _MAX_ITERATIONS) -> str:
    """Run the agentic loop for a single voice command.

    Always injects a screenshot into the first user message and after every
    action tool, so Claude always has current screen context before reasoning.

    Returns a human-readable summary of what was accomplished.
    """
    client = _make_client()
    system = _build_system_prompt()

    # Inject an initial screenshot so Claude sees the screen from the very start.
    print(f"[planner] goal={command.text!r} — capturing initial screenshot")
    initial_screenshot = await asyncio.to_thread(_screenshot_image_block)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": command.text},
                {"type": "text", "text": "Current screen:"},
                initial_screenshot,
            ],
        }
    ]

    for iteration in range(max_iterations):
        print(f"[planner] iteration={iteration + 1}/{max_iterations}")

        response = await asyncio.to_thread(
            client.messages.create,
            model=_MODEL,
            max_tokens=4096,
            system=system,
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
        ran_action = False

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
                if name in _ACTION_TOOLS:
                    ran_action = True
                payload = result.result if result.ok else result.error
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(payload),
                })

        # After any action tool, automatically append a fresh screenshot so
        # Claude sees the updated screen state before its next reasoning step.
        if ran_action and not finished:
            print("[planner] capturing post-action screenshot")
            post_shot = await asyncio.to_thread(_screenshot_image_block)
            tool_results.append({"type": "text", "text": "Screen after your actions:"})
            tool_results.append(post_shot)

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
