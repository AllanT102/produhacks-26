"""Individual tool implementations and dispatch registry."""

from src.tool_runtime.tools.click import click, double_click
from src.tool_runtime.tools.keyboard import key_press, type_text
from src.tool_runtime.tools.mouse import drag, move_to
from src.tool_runtime.tools.screenshot import screenshot
from src.tool_runtime.tools.scroll import scroll

# Maps tool name → callable. Tool names must match the Claude tool schemas exactly.
REGISTRY: dict = {
    "screenshot": screenshot,
    "click": click,
    "double_click": double_click,
    "scroll": scroll,
    "type_text": type_text,
    "key_press": key_press,
    "move_to": move_to,
    "drag": drag,
}
