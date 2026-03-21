"""Individual tool implementations and dispatch registry."""

from src.tool_runtime.tools.browser import get_manager  # noqa: F401 — ensures manager is importable
from src.tool_runtime.tools.screenshot import screenshot
from src.tool_runtime.tools.navigate import navigate
from src.tool_runtime.tools.click import click
from src.tool_runtime.tools.find_elements import find_elements
from src.tool_runtime.tools.type_text import type_text
from src.tool_runtime.tools.scroll import scroll
from src.tool_runtime.tools.key_press import key_press
from src.tool_runtime.tools.get_page_info import get_page_info
from src.tool_runtime.tools.tab_ops import open_tab, close_tab
from src.tool_runtime.tools.brightness import set_brightness
from src.tool_runtime.tools.volume import set_volume

# Maps tool name → callable. Tool names must match the Claude tool schemas exactly.
REGISTRY: dict = {
    "screenshot": screenshot,
    "navigate": navigate,
    "click": click,
    "find_elements": find_elements,
    "type_text": type_text,
    "scroll": scroll,
    "key_press": key_press,
    "get_page_info": get_page_info,
    "open_tab": open_tab,
    "close_tab": close_tab,
    "set_volume": set_volume,
    "set_brightness": set_brightness,
    # task_complete is handled specially in planner.py — not dispatched via REGISTRY
}
