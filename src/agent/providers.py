"""LLM provider abstraction for the desktop agent.

Supports Anthropic, OpenAI, and Gemini (via OpenAI-compatible endpoint).
Each provider normalizes message formatting, tool schemas, and image blocks
so the planner loop has no provider-specific logic.
"""

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from src.tool_runtime.schemas import TOOLS as _ANTHROPIC_TOOLS


# ---------------------------------------------------------------------------
# Shared data types returned by every provider
# ---------------------------------------------------------------------------

@dataclass
class ToolUse:
    id: str
    name: str
    inputs: dict


@dataclass
class LLMResponse:
    tool_uses: list = field(default_factory=list)  # list[ToolUse]
    text: Optional[str] = None                     # set when stop_reason is end_turn


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class LLMProvider(ABC):

    @abstractmethod
    def complete(self, messages: list, system: str) -> tuple:
        """Make one API call. Returns (LLMResponse, raw_response)."""

    @abstractmethod
    def append_assistant_turn(self, messages: list, raw: Any) -> None:
        """Append the assistant's raw response to the message history."""

    @abstractmethod
    def append_tool_results(
        self,
        messages: list,
        tool_uses: list,
        results: list,
        post_screenshot: Optional[dict],
    ) -> None:
        """Append tool results (and optional post-action screenshot) to history.

        results[i] is either:
          - a JSON string  (for action tools)
          - a screenshot dict {"_is_screenshot": True, "data": ..., "media_type": ...}
        """

    @abstractmethod
    def format_screenshot(self, data: str, media_type: str) -> dict:
        """Return a screenshot as a provider-specific image content block."""

    @abstractmethod
    def initial_user_message(self, text: str, screenshot_block: dict) -> dict:
        """Build the first user message: task text + initial screenshot."""


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

class AnthropicProvider(LLMProvider):

    def __init__(self, model: str = "claude-opus-4-6", api_key: Optional[str] = None):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self._model = model

    def complete(self, messages: list, system: str) -> tuple:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            tools=_ANTHROPIC_TOOLS,
            messages=messages,
        )
        tool_uses = [
            ToolUse(id=b.id, name=b.name, inputs=b.input)
            for b in response.content
            if b.type == "tool_use"
        ]
        text = next((b.text for b in response.content if hasattr(b, "text")), None)
        return LLMResponse(tool_uses=tool_uses, text=text), response

    def append_assistant_turn(self, messages: list, raw: Any) -> None:
        messages.append({"role": "assistant", "content": raw.content})

    def append_tool_results(self, messages, tool_uses, results, post_screenshot):
        content = []
        for use, result in zip(tool_uses, results):
            if isinstance(result, dict) and result.get("_is_screenshot"):
                img = self.format_screenshot(result["data"], result["media_type"])
                content.append({"type": "tool_result", "tool_use_id": use.id, "content": [img]})
            else:
                content.append({"type": "tool_result", "tool_use_id": use.id, "content": result})
        if post_screenshot:
            content.append({"type": "text", "text": "Screen after your actions:"})
            content.append(self.format_screenshot(post_screenshot["data"], post_screenshot["media_type"]))
        messages.append({"role": "user", "content": content})

    def format_screenshot(self, data: str, media_type: str) -> dict:
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        }

    def initial_user_message(self, text: str, screenshot_block: dict) -> dict:
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {"type": "text", "text": "Current screen:"},
                screenshot_block,
            ],
        }


# ---------------------------------------------------------------------------
# OpenAI-compatible (OpenAI + Gemini share this implementation)
# ---------------------------------------------------------------------------

def _to_openai_tools(anthropic_tools: list) -> list:
    """Convert Anthropic tool schema format to OpenAI function format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in anthropic_tools
    ]


_OPENAI_TOOLS = _to_openai_tools(_ANTHROPIC_TOOLS)


class OpenAICompatibleProvider(LLMProvider):

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def complete(self, messages: list, system: str) -> tuple:
        all_messages = [{"role": "system", "content": system}] + messages
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=4096,
            tools=_OPENAI_TOOLS,
            messages=all_messages,
        )
        msg = response.choices[0].message
        tool_uses = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_uses.append(ToolUse(
                    id=tc.id,
                    name=tc.function.name,
                    inputs=json.loads(tc.function.arguments),
                ))
        text = msg.content if not msg.tool_calls else None
        return LLMResponse(tool_uses=tool_uses, text=text), msg

    def append_assistant_turn(self, messages: list, raw: Any) -> None:
        # Serialize to a plain dict so the history stays JSON-serialisable.
        tool_calls = None
        if raw.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in raw.tool_calls
            ]
        messages.append({
            "role": "assistant",
            "content": raw.content,
            "tool_calls": tool_calls,
        })

    def append_tool_results(self, messages, tool_uses, results, post_screenshot):
        # OpenAI tool results are individual messages with role "tool".
        screenshot_images = []
        for use, result in zip(tool_uses, results):
            if isinstance(result, dict) and result.get("_is_screenshot"):
                # Tool result must be a string; send the image separately below.
                messages.append({
                    "role": "tool",
                    "tool_call_id": use.id,
                    "content": "[screenshot captured — see image below]",
                })
                screenshot_images.append(self.format_screenshot(result["data"], result["media_type"]))
            else:
                messages.append({
                    "role": "tool",
                    "tool_call_id": use.id,
                    "content": result,
                })

        # Inject any screenshot images (explicit calls + post-action) as a user message.
        images_to_show = screenshot_images
        if post_screenshot:
            images_to_show = images_to_show + [
                self.format_screenshot(post_screenshot["data"], post_screenshot["media_type"])
            ]
        if images_to_show:
            content = [{"type": "text", "text": "Current screen:"}] + images_to_show
            messages.append({"role": "user", "content": content})

    def format_screenshot(self, data: str, media_type: str) -> dict:
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{data}"},
        }

    def initial_user_message(self, text: str, screenshot_block: dict) -> dict:
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {"type": "text", "text": "Current screen:"},
                screenshot_block,
            ],
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_provider(
    provider: str = "anthropic",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> LLMProvider:
    """Instantiate a provider by name.

    provider: "anthropic" | "openai" | "gemini"
    model:    override the default model for that provider
    api_key:  override; falls back to the relevant env var per provider
    """
    p = provider.lower().strip()

    if p == "anthropic":
        return AnthropicProvider(
            model=model or "claude-opus-4-6",
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
        )

    if p == "openai":
        return OpenAICompatibleProvider(
            model=model or "gpt-4o",
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        )

    if p == "gemini":
        return OpenAICompatibleProvider(
            model=model or "gemini-2.0-flash",
            api_key=api_key or os.environ.get("GEMINI_API_KEY"),
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )

    raise ValueError(f"Unknown provider {p!r}. Choose: anthropic, openai, gemini")
