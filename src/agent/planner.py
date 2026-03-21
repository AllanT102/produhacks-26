"""Claude-powered agentic loop: transcript -> tool calls -> desktop actions."""

import asyncio
import json
import os
from typing import Callable, Optional

import anthropic

from src.shared.events import AgentCommand, ToolCall, ToolResult
from src.tool_runtime.runtime import execute_tool
from src.tool_runtime.schemas import TOOLS

_MODEL = "claude-opus-4-6"
_MAX_ITERATIONS = 12
_MAX_CONSECUTIVE_NON_ACTION_ROUNDS = 2

_ACTION_TOOLS = {
    "click",
    "click_target",
    "double_click",
    "scroll",
    "type_text",
    "key_press",
    "move_to",
    "drag",
}

ToolExecutor = Callable[[ToolCall], ToolResult]


def _make_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def _build_system_prompt() -> str:
    base = [
        "You are a macOS desktop automation agent.",
        "You can only act by calling the provided tools.",
        "Take one small action at a time.",
        "Use screenshot before acting when you need to inspect the UI.",
        "When the user asks to open an app or open a known website in a browser, prefer open_app instead of clicking around manually.",
        "Prefer propose_targets plus click_target over raw click coordinates whenever you need to select something visible on screen.",
        "Never guess coordinates. Ground every action in the visible screen.",
        "After any action that changes the UI, you will be shown an updated screenshot.",
        "As soon as that updated screenshot shows the user's goal is achieved, you MUST immediately call task_complete.",
        "Do not request another screenshot right after a post-action screenshot unless the screenshot was missing or unusable.",
        "If the goal is already visible on screen, finish immediately with task_complete instead of taking more actions.",
    ]

    try:
        import pyautogui

        width, height = pyautogui.size()
        base.append(f"Screen resolution: {width}x{height} pixels. Keep coordinates within those bounds.")
    except Exception:
        pass

    return "\n".join(base)


def _screenshot_content(result: ToolResult) -> list[dict]:
    """Convert a screenshot tool result into Anthropic message blocks."""
    if not result.ok or not result.result:
        message = "screenshot failed"
        if result.error and result.error.get("message"):
            message = f"screenshot failed: {result.error['message']}"
        return [{"type": "text", "text": f"[{message}]"}]

    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": result.result["media_type"],
                "data": result.result["data"],
            },
        }
    ]
    if result.result.get("text"):
        content.append({
            "type": "text",
            "text": result.result["text"],
        })
    return content


def _summarize_visible_state(result: ToolResult) -> Optional[str]:
    """Extract any textual screen summary provided by the screenshot tool."""
    if not result.ok or not result.result:
        return None
    text = result.result.get("text")
    if isinstance(text, str):
        return text.strip()
    return None


async def execute_command(command: AgentCommand, max_iterations: int = _MAX_ITERATIONS) -> str:
    """Run the agentic loop for a single voice command with real desktop tools."""
    return await execute_command_with_tools(command, execute_tool, max_iterations=max_iterations)


async def execute_command_with_tools(
    command: AgentCommand,
    tool_executor: ToolExecutor,
    max_iterations: int = _MAX_ITERATIONS,
) -> str:
    """Run the agentic loop for a single voice command with an injected tool executor."""
    client = _make_client()
    system = _build_system_prompt()
    consecutive_non_action_rounds = 0
    post_action_verification_sent = False

    print(f"[planner] goal={command.text!r} — capturing initial screenshot")
    initial_result = await asyncio.to_thread(tool_executor, ToolCall(tool="screenshot", args={}))
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": command.text},
                {"type": "text", "text": "Current screen:"},
                *_screenshot_content(initial_result),
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
        screenshot_requests = 0

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

            result = await asyncio.to_thread(tool_executor, ToolCall(tool=name, args=inputs))

            if name == "screenshot":
                screenshot_requests += 1
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": _screenshot_content(result),
                })
                continue

            if name in _ACTION_TOOLS:
                ran_action = True

            payload = result.result if result.ok else result.error
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(payload),
            })

        if ran_action:
            consecutive_non_action_rounds = 0
        elif not finished:
            consecutive_non_action_rounds += 1

        if post_action_verification_sent and not ran_action and not finished:
            return (
                "Stopped after showing the updated screen because the planner did not complete "
                "the task or take a new action."
            )

        if (
            screenshot_requests > 0
            and not ran_action
            and not finished
            and consecutive_non_action_rounds >= _MAX_CONSECUTIVE_NON_ACTION_ROUNDS
        ):
            return "Stopped after repeated screenshot-only reasoning without progress."

        if consecutive_non_action_rounds >= _MAX_CONSECUTIVE_NON_ACTION_ROUNDS and not finished:
            return "Stopped after multiple reasoning rounds without any new action."

        if ran_action and not finished:
            await asyncio.sleep(0.5)
            print("[planner] capturing post-action screenshot")
            post_result = await asyncio.to_thread(tool_executor, ToolCall(tool="screenshot", args={}))
            visible_state = _summarize_visible_state(post_result)
            tool_results.append({"type": "text", "text": "Screen after your actions:"})
            tool_results.extend(_screenshot_content(post_result))
            if visible_state:
                tool_results.append({
                    "type": "text",
                    "text": (
                        "If this updated screen already satisfies the user's goal, call task_complete now. "
                        f"Visible state summary: {visible_state}"
                    ),
                })
            post_action_verification_sent = True
        else:
            post_action_verification_sent = False

        messages.append({"role": "user", "content": tool_results})

        if finished:
            print(f"[planner] done — {summary}")
            return summary

    return f"Reached {max_iterations} iterations without completing the task."


def plan_from_transcript(text: str) -> dict:
    """Deprecated: returns a stub plan. Use execute_command() instead."""
    return {
        "goal": text.strip(),
        "steps": [{"type": "reason", "status": "pending"}],
    }
