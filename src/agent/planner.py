"""Gemini-powered agentic loop: transcript → tool calls → desktop actions."""

import asyncio
import json
import os

import pyautogui
from openai import OpenAI

from src.shared.events import AgentCommand, ToolCall
from src.tool_runtime.runtime import execute_tool
from src.tool_runtime.schemas import TOOLS as _ANTHROPIC_TOOLS
from src.tool_runtime.tools.screenshot import screenshot

_MODEL = "gemini-2.0-flash"
_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
_MAX_ITERATIONS = 20

_ACTION_TOOLS = {"click", "double_click", "scroll", "type_text", "key_press", "move_to", "drag"}

# Convert Anthropic tool schema format → OpenAI function format once at import.
_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        },
    }
    for t in _ANTHROPIC_TOOLS
]


def _make_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ.get("GEMINI_API_KEY"),
        base_url=_BASE_URL,
    )


def _build_system_prompt() -> str:
    w, h = pyautogui.size()
    return (
        f"You are a macOS desktop automation agent.\n"
        f"Screen resolution: {w}x{h} pixels. All coordinates must be within these bounds.\n"
        f"You will always be shown the current screen before acting. "
        f"Use the pixel coordinates visible in the screenshot to decide where to click, "
        f"scroll, or type. Never guess coordinates — always ground them in what you see.\n"
        f"When the user's goal is fully achieved, call task_complete."
    )


def _screenshot_image_block() -> dict:
    """Capture a screenshot and return an OpenAI-format image_url content block."""
    result = screenshot()
    if not result["ok"]:
        return {"type": "text", "text": f"[screenshot failed: {result['error']}]"}
    data = result["data"]
    media_type = result["media_type"]
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{media_type};base64,{data}"},
    }


async def execute_command(command: AgentCommand, max_iterations: int = _MAX_ITERATIONS) -> str:
    """Run the agentic loop for a single voice command.

    Returns a human-readable summary of what was accomplished.
    """
    client = _make_client()
    system = _build_system_prompt()

    print(f"[planner] goal={command.text!r} — capturing initial screenshot")
    initial_screenshot = await asyncio.to_thread(_screenshot_image_block)

    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": command.text},
                {"type": "text", "text": "Current screen:"},
                initial_screenshot,
            ],
        },
    ]

    for iteration in range(max_iterations):
        print(f"[planner] iteration={iteration + 1}/{max_iterations}")

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=_MODEL,
            max_tokens=4096,
            tools=_TOOLS,
            messages=messages,
        )

        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        # Append assistant turn — preserve tool_calls so the API can match results.
        assistant_turn = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            assistant_turn["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_turn)

        if finish_reason == "stop" or not msg.tool_calls:
            return msg.content or "Done."

        # --- dispatch tool calls ---
        finished = False
        summary = ""
        ran_action = False
        screenshot_images = []  # explicit screenshot results to surface as a user message

        for tc in msg.tool_calls:
            name = tc.function.name
            inputs = json.loads(tc.function.arguments)
            print(f"[planner] tool={name} inputs={inputs}")

            if name == "task_complete":
                summary = inputs.get("summary", "Task complete.")
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": summary})
                finished = True
                continue

            result = await asyncio.to_thread(
                execute_tool, ToolCall(tool=name, args=inputs)
            )

            if name == "screenshot" and result.ok and result.result:
                # Tool result must be a string; send the actual image separately below.
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": "[screenshot captured — see image below]",
                })
                screenshot_images.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{result.result['media_type']};base64,{result.result['data']}"
                    },
                })
            else:
                if name in _ACTION_TOOLS:
                    ran_action = True
                payload = result.result if result.ok else result.error
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(payload),
                })

        # Surface screenshot images + post-action screenshot as a user message.
        if ran_action and not finished:
            print("[planner] capturing post-action screenshot")
            screenshot_images.append(await asyncio.to_thread(_screenshot_image_block))

        if screenshot_images:
            messages.append({
                "role": "user",
                "content": [{"type": "text", "text": "Current screen:"}] + screenshot_images,
            })

        if finished:
            print(f"[planner] done — {summary}")
            return summary

    return f"Reached {max_iterations} iterations without completing the task."


def plan_from_transcript(text: str) -> dict:
    """Deprecated stub. Use execute_command() instead."""
    return {"goal": text.strip(), "steps": [{"type": "reason", "status": "pending"}]}
