"""Deterministic mock tool executor for local planner experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.shared.events import ToolCall, ToolResult

_ONE_BY_ONE_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WnY3QAAAABJRU5ErkJggg=="
)


@dataclass
class MockScenarioState:
    name: str
    screen: str
    focused: Optional[str] = None
    typed_text: str = ""
    step_count: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)


class MockExecutor:
    """Simple state machine for planner-only experiments."""

    def __init__(self, scenario: str) -> None:
        if scenario not in {"youtube_search", "youtube_open_first"}:
            raise ValueError(f"Unknown mock scenario: {scenario}")
        self.state = MockScenarioState(name=scenario, screen="home")

    def execute(self, call: ToolCall) -> ToolResult:
        self.state.step_count += 1
        self.state.history.append({"tool": call.tool, "args": call.args})

        handlers = {
            "screenshot": self._screenshot,
            "navigate": self._navigate,
            "click": self._click,
            "find_elements": self._find_elements,
            "type_text": self._type_text,
            "key_press": self._key_press,
            "scroll": self._scroll,
            "get_page_info": self._get_page_info,
            "open_tab": self._open_tab,
            "close_tab": self._close_tab,
        }
        handler = handlers.get(call.tool)
        if handler is None:
            return ToolResult(
                ok=False,
                tool=call.tool,
                error={"code": "UNKNOWN_TOOL", "message": f"Unsupported mock tool: {call.tool}"},
            )
        return handler(call)

    def _screen_text(self) -> str:
        if self.state.name == "youtube_search":
            if self.state.screen == "home":
                return (
                    "Current screen: YouTube home page. Search input is visible near the top center. "
                    "Approximate clickable center is x=640 y=84."
                )
            if self.state.screen == "search_focused":
                return (
                    "Current screen: YouTube home page with the search input focused. "
                    f"Current draft query is '{self.state.typed_text}'."
                )
            if self.state.screen == "results":
                return (
                    "Current screen: YouTube search results page for "
                    f"'{self.state.typed_text}'. The first result is visible near x=560 y=220."
                )
        if self.state.name == "youtube_open_first":
            if self.state.screen == "home":
                return (
                    "Current screen: YouTube search results page. "
                    "The first video result is visible near x=560 y=220."
                )
            if self.state.screen == "video_open":
                return "Current screen: YouTube video page is open and playing."
        return "Current screen: unknown."

    def _screenshot(self, call: ToolCall) -> ToolResult:
        del call
        return ToolResult(
            ok=True,
            tool="screenshot",
            result={
                "data": _ONE_BY_ONE_PNG_BASE64,
                "media_type": "image/png",
                "text": self._screen_text(),
            },
        )

    def _navigate(self, call: ToolCall) -> ToolResult:
        url = call.args.get("url")
        if url:
            self.state.screen = "navigated"
            self.state.focused = None
            return ToolResult(ok=True, tool="navigate", result={"ok": True, "url": url})
        return ToolResult(ok=True, tool="navigate", result={"ok": True, "url": "about:blank"})

    def _click(self, call: ToolCall) -> ToolResult:
        desc = call.args.get("description", "").lower()
        if self.state.screen == "home" and "search" in desc:
            self.state.screen = "search_focused"
            self.state.focused = "search_input"
            return ToolResult(ok=True, tool="click", result={"ok": True, "description": desc, "effect": "focused_search"})
        if self.state.screen == "results" and ("first" in desc or "result" in desc or "video" in desc):
            self.state.screen = "video_open"
            return ToolResult(ok=True, tool="click", result={"ok": True, "description": desc, "effect": "opened_first_result"})
        return ToolResult(
            ok=False,
            tool="click",
            error={"code": "MISS", "message": f"Click description={desc!r} did not match a mock target."},
        )

    def _find_elements(self, call: ToolCall) -> ToolResult:
        query = str(call.args.get("query", "")).lower()
        if self.state.name == "youtube_search" and "search" in query:
            return ToolResult(
                ok=True,
                tool="find_elements",
                result={
                    "ok": True,
                    "elements": [
                        {"element_id": "mock_search_box", "text": "Search", "tag": "input", "role": "searchbox"},
                    ],
                },
            )
        if self.state.screen == "results" and ("first" in query or "result" in query):
            return ToolResult(
                ok=True,
                tool="find_elements",
                result={
                    "ok": True,
                    "elements": [
                        {"element_id": "mock_first_result", "text": "First video result", "tag": "a", "role": "link"},
                    ],
                },
            )
        return ToolResult(ok=True, tool="find_elements", result={"ok": True, "elements": []})

    def _type_text(self, call: ToolCall) -> ToolResult:
        text = str(call.args["text"])
        if self.state.focused != "search_input":
            return ToolResult(
                ok=False,
                tool="type_text",
                error={"code": "NOT_FOCUSED", "message": "No text input is focused."},
            )
        self.state.typed_text += text
        return ToolResult(ok=True, tool="type_text", result={"ok": True, "text": text})

    def _key_press(self, call: ToolCall) -> ToolResult:
        key = str(call.args["key"]).lower()
        if key in ("enter", "return") and self.state.screen == "search_focused" and self.state.typed_text:
            self.state.screen = "results"
            self.state.focused = None
            return ToolResult(ok=True, tool="key_press", result={"ok": True, "key": key, "effect": "submitted_search"})
        return ToolResult(ok=True, tool="key_press", result={"ok": True, "key": key})

    def _scroll(self, call: ToolCall) -> ToolResult:
        return ToolResult(ok=True, tool="scroll", result={"ok": True, "args": call.args})

    def _get_page_info(self, call: ToolCall) -> ToolResult:
        del call
        return ToolResult(
            ok=True,
            tool="get_page_info",
            result={"ok": True, "url": "https://mock.example.com", "title": "Mock Page", "text": self._screen_text()},
        )

    def _open_tab(self, call: ToolCall) -> ToolResult:
        url = call.args.get("url", "about:blank")
        return ToolResult(ok=True, tool="open_tab", result={"ok": True, "url": url})

    def _close_tab(self, call: ToolCall) -> ToolResult:
        del call
        return ToolResult(ok=True, tool="close_tab", result={"ok": True, "url": "about:blank"})
