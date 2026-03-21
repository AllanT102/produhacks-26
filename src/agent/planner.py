"""Claude-powered agentic loop: transcript → tool calls → desktop actions."""

import asyncio
import json
import os
from typing import Optional

import pyautogui

from src.agent.providers import LLMProvider, make_provider
from src.shared.events import AgentCommand, ToolCall
from src.tool_runtime.runtime import execute_tool
from src.tool_runtime.tools.screenshot import screenshot

_MAX_ITERATIONS = 20

# Tools that act on the desktop — a post-action screenshot is auto-injected after these.
_ACTION_TOOLS = {"click", "double_click", "scroll", "type_text", "key_press", "move_to", "drag"}


def _build_system_prompt() -> str:
    w, h = pyautogui.size()
    return (
        f"You are a macOS desktop automation agent.\n"
        f"Screen resolution: {w}x{h} pixels. All coordinates must be within this bounds.\n"
        f"You will always be shown the current screen before acting. "
        f"Use the pixel coordinates visible in the screenshot to decide where to click, "
        f"scroll, or type. Never guess coordinates — always ground them in what you see.\n"
        f"When the user's goal is fully achieved, call task_complete."
    )


async def _take_screenshot() -> dict:
    """Capture a screenshot and return a raw dict for provider formatting."""
    result = await asyncio.to_thread(screenshot)
    if not result["ok"]:
        return {"_screenshot_failed": True, "error": result.get("error")}
    return {"_is_screenshot": True, "data": result["data"], "media_type": result["media_type"]}


async def execute_command(
    command: AgentCommand,
    provider: Optional[LLMProvider] = None,
    max_iterations: int = _MAX_ITERATIONS,
) -> str:
    """Run the agentic loop for a single voice command.

    provider: an LLMProvider instance; defaults to reading AGENT_PROVIDER /
              AGENT_MODEL env vars (falls back to Anthropic claude-opus-4-6).

    Returns a human-readable summary of what was accomplished.
    """
    if provider is None:
        provider = make_provider(
            provider=os.environ.get("AGENT_PROVIDER", "anthropic"),
            model=os.environ.get("AGENT_MODEL") or None,
        )

    system = _build_system_prompt()

    print(f"[planner] goal={command.text!r} — capturing initial screenshot")
    initial_shot = await _take_screenshot()
    initial_block = provider.format_screenshot(initial_shot["data"], initial_shot["media_type"])

    messages = [provider.initial_user_message(command.text, initial_block)]

    for iteration in range(max_iterations):
        print(f"[planner] iteration={iteration + 1}/{max_iterations}")

        llm_response, raw = await asyncio.to_thread(provider.complete, messages, system)

        provider.append_assistant_turn(messages, raw)

        # No tool calls — Claude wrote a plain response, we're done.
        if not llm_response.tool_uses:
            return llm_response.text or "Done."

        results = []
        finished = False
        summary = ""
        ran_action = False

        for use in llm_response.tool_uses:
            print(f"[planner] tool={use.name} inputs={use.inputs}")

            if use.name == "task_complete":
                summary = use.inputs.get("summary", "Task complete.")
                results.append(summary)
                finished = True
                continue

            tool_result = await asyncio.to_thread(
                execute_tool, ToolCall(tool=use.name, args=use.inputs)
            )

            if use.name == "screenshot" and tool_result.ok and tool_result.result:
                # Pass the raw screenshot dict so the provider can format it correctly.
                results.append({
                    "_is_screenshot": True,
                    "data": tool_result.result["data"],
                    "media_type": tool_result.result["media_type"],
                })
            else:
                if use.name in _ACTION_TOOLS:
                    ran_action = True
                payload = tool_result.result if tool_result.ok else tool_result.error
                results.append(json.dumps(payload))

        # Auto-inject a fresh screenshot after any action so Claude sees the result.
        post_shot = None
        if ran_action and not finished:
            print("[planner] capturing post-action screenshot")
            post_shot = await _take_screenshot()

        provider.append_tool_results(messages, llm_response.tool_uses, results, post_shot)

        if finished:
            print(f"[planner] done — {summary}")
            return summary

    return f"Reached {max_iterations} iterations without completing the task."


# ---------------------------------------------------------------------------
# Legacy synchronous shim — kept so existing imports don't break.
# ---------------------------------------------------------------------------

def plan_from_transcript(text: str) -> dict:
    """Deprecated: returns a stub plan. Use execute_command() instead."""
    return {
        "goal": text.strip(),
        "steps": [{"type": "reason", "status": "pending"}],
    }
