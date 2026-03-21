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
            "click": self._click,
            "click_target": self._click_target,
            "double_click": self._double_click,
            "propose_targets": self._propose_targets,
            "type_text": self._type_text,
            "key_press": self._key_press,
            "scroll": self._scroll,
            "move_to": self._move_to,
            "drag": self._drag,
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

    def _click(self, call: ToolCall) -> ToolResult:
        x = int(call.args["x"])
        y = int(call.args["y"])
        if self.state.screen == "home" and abs(x - 640) <= 140 and abs(y - 84) <= 50:
            self.state.screen = "search_focused"
            self.state.focused = "search_input"
            return ToolResult(ok=True, tool="click", result={"x": x, "y": y, "effect": "focused_search"})
        if self.state.screen == "results" and abs(x - 560) <= 220 and abs(y - 220) <= 80:
            self.state.screen = "video_open"
            return ToolResult(ok=True, tool="click", result={"x": x, "y": y, "effect": "opened_first_result"})
        return ToolResult(
            ok=False,
            tool="click",
            error={"code": "MISS", "message": f"Click at ({x}, {y}) did not hit a useful target."},
        )

    def _propose_targets(self, call: ToolCall) -> ToolResult:
        query = str(call.args["query"]).lower()
        if self.state.name == "youtube_search" and "search" in query:
            return ToolResult(
                ok=True,
                tool="propose_targets",
                result={
                    "query": query,
                    "targets": [
                        {
                            "target_id": "mock_search_box",
                            "label": "YouTube search input",
                            "role": "input",
                            "source": "mock",
                            "bbox": {"x": 500, "y": 60, "width": 280, "height": 48},
                            "center": {"x": 640, "y": 84},
                            "confidence": 0.99,
                        }
                    ],
                },
            )
        if self.state.screen == "results" and "first" in query:
            return ToolResult(
                ok=True,
                tool="propose_targets",
                result={
                    "query": query,
                    "targets": [
                        {
                            "target_id": "mock_first_result",
                            "label": "First result",
                            "role": "result",
                            "source": "mock",
                            "bbox": {"x": 340, "y": 180, "width": 440, "height": 80},
                            "center": {"x": 560, "y": 220},
                            "confidence": 0.99,
                        }
                    ],
                },
            )
        return ToolResult(
            ok=False,
            tool="propose_targets",
            error={"code": "NOT_FOUND", "message": f"No mock target for query '{query}'"},
        )

    def _click_target(self, call: ToolCall) -> ToolResult:
        target_id = str(call.args["target_id"])
        mapping = {
            "mock_search_box": {"x": 640, "y": 84},
            "mock_first_result": {"x": 560, "y": 220},
        }
        coords = mapping.get(target_id)
        if not coords:
            return ToolResult(
                ok=False,
                tool="click_target",
                error={"code": "NOT_FOUND", "message": f"Unknown mock target '{target_id}'"},
            )
        return self._click(ToolCall(tool="click", args=coords))

    def _double_click(self, call: ToolCall) -> ToolResult:
        return self._click(call)

    def _type_text(self, call: ToolCall) -> ToolResult:
        text = str(call.args["text"])
        if self.state.focused != "search_input":
            return ToolResult(
                ok=False,
                tool="type_text",
                error={"code": "NOT_FOCUSED", "message": "No text input is focused."},
            )
        self.state.typed_text += text
        return ToolResult(ok=True, tool="type_text", result={"text": text})

    def _key_press(self, call: ToolCall) -> ToolResult:
        key = str(call.args["key"]).lower()
        if key == "enter" and self.state.screen == "search_focused" and self.state.typed_text:
            self.state.screen = "results"
            self.state.focused = None
            return ToolResult(ok=True, tool="key_press", result={"key": key, "effect": "submitted_search"})
        return ToolResult(ok=True, tool="key_press", result={"key": key})

    def _scroll(self, call: ToolCall) -> ToolResult:
        return ToolResult(ok=True, tool="scroll", result={"args": call.args})

    def _move_to(self, call: ToolCall) -> ToolResult:
        return ToolResult(ok=True, tool="move_to", result={"args": call.args})

    def _drag(self, call: ToolCall) -> ToolResult:
        return ToolResult(ok=True, tool="drag", result={"args": call.args})
