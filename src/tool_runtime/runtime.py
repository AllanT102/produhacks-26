"""Tool runtime surface."""

from src.shared.events import ToolCall, ToolResult
from src.tool_runtime.tools import REGISTRY


def execute_tool(call: ToolCall) -> ToolResult:
    """Dispatch a ToolCall to the matching pyautogui implementation."""
    fn = REGISTRY.get(call.tool)
    if fn is None:
        return ToolResult(
            ok=False,
            tool=call.tool,
            error={"code": "UNKNOWN_TOOL", "message": f"No implementation for tool '{call.tool}'"},
        )
    try:
        raw = fn(**call.args)
        if raw.get("ok"):
            return ToolResult(ok=True, tool=call.tool, result=raw)
        return ToolResult(
            ok=False,
            tool=call.tool,
            error={"code": "TOOL_ERROR", "message": raw.get("error", "unknown error")},
        )
    except TypeError as exc:
        return ToolResult(
            ok=False,
            tool=call.tool,
            error={"code": "BAD_ARGS", "message": str(exc)},
        )
    except Exception as exc:
        return ToolResult(
            ok=False,
            tool=call.tool,
            error={"code": "RUNTIME_ERROR", "message": str(exc)},
        )
