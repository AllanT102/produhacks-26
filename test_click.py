"""Quick test: fire a click tool call through the full dispatch chain."""
import time
from src.shared.events import ToolCall
from src.tool_runtime.runtime import execute_tool

time.sleep(2)  # time to switch focus away from terminal
result = execute_tool(ToolCall(tool="click", args={"x": 840, "y": 1081}))
print(result)
