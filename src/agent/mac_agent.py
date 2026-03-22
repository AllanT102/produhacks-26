"""Unified Mac agent: uses Claude + all tool_runtime tools to handle any desktop task."""

from __future__ import annotations

import json
import time
from typing import Any

import anthropic

from src.shared.events import AgentCommand, ToolCall
from src.shared.timing import elapsed_ms
from src.tool_runtime.runtime import execute_tool
from src.tool_runtime.schemas import TOOLS

MAX_ITERATIONS = 20

_SYSTEM_PROMPT = """You are a macOS voice control agent. You execute the user's spoken commands by choosing and calling the right tools.

Guidelines:
- Take a screenshot first whenever you need to see the current screen state before acting.
- Prefer specific app tools (e.g. spotify_play, set_volume) over visual automation when available — they are faster and more reliable.
- For UI interactions, use propose_targets to find elements semantically before guessing raw coordinates.
- Use browser tools (browser_query, browser_click_ref, etc.) when interacting with web content in Google Chrome.
- Chain multiple tool calls as needed to complete multi-step tasks.
- When the goal is fully achieved, call task_complete with a brief summary.
- Keep actions focused and minimal — do not do more than the user asked.
"""


def _tool_result_content(tool_use_id: str, result: dict[str, Any]) -> dict:
    # If screenshot, return image content block
    if result.get("tool") == "screenshot" and result.get("result", {}).get("ok"):
        data = result["result"].get("data")
        media_type = result["result"].get("media_type", "image/png")
        if data:
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": [{"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}],
            }
    # Otherwise serialize as text
    if result.get("ok"):
        content = json.dumps(result.get("result") or {"ok": True})
    else:
        content = json.dumps(result.get("error") or {"ok": False})
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
        "is_error": not result.get("ok", True),
    }


async def execute_command_with_mac_agent(command: AgentCommand) -> str:
    started_at = time.perf_counter()
    client = anthropic.Anthropic()
    messages: list[dict] = [{"role": "user", "content": command.text}]

    summary = "Done."

    for iteration in range(MAX_ITERATIONS):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            tools=TOOLS,
            system=_SYSTEM_PROMPT,
            messages=messages,
        )

        # Append assistant turn
        messages.append({"role": "assistant", "content": response.content})

        tool_uses = [block for block in response.content if block.type == "tool_use"]

        if not tool_uses:
            # No tool calls — extract text as summary
            for block in response.content:
                if hasattr(block, "text") and block.text:
                    summary = block.text.strip()
            break

        # Execute all tool calls and collect results
        tool_results = []
        for block in tool_uses:
            tool_name = block.name
            tool_args = block.input or {}

            if tool_name == "task_complete":
                summary = tool_args.get("summary", "Done.")
                print(f"[mac_agent] task_complete after {iteration + 1} iteration(s): {summary}")
                print("[timing] mac_agent took {:.1f}ms".format(elapsed_ms(started_at)))
                return summary

            print(f"[mac_agent] calling tool={tool_name} args={tool_args}")
            call = ToolCall(tool=tool_name, args=tool_args)
            result = execute_tool(call)

            tool_results.append(_tool_result_content(block.id, {
                "ok": result.ok,
                "tool": result.tool,
                "result": result.result,
                "error": result.error,
            }))

        messages.append({"role": "user", "content": tool_results})

    print("[timing] mac_agent took {:.1f}ms".format(elapsed_ms(started_at)))
    return summary
