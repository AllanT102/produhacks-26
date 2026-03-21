"""Tool runtime surface."""

from src.shared.events import ToolCall, ToolResult


def execute_tool(call: ToolCall) -> ToolResult:
    """Execute a tool call. Placeholder until real Mac actions are implemented."""
    return ToolResult(
        ok=False,
        tool=call.tool,
        error={"code": "NOT_IMPLEMENTED", "message": "Tool runtime not implemented yet."},
    )
