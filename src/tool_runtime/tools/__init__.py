"""Individual tool implementations and dispatch registry."""

from src.tool_runtime.tools.click import click, double_click
from src.tool_runtime.tools.keyboard import key_press, type_text
from src.tool_runtime.tools.mouse import drag, move_to
from src.tool_runtime.tools.app import open_app
from src.tool_runtime.tools.browser import (
    browser_click_ref,
    browser_extract_text,
    browser_fill_ref,
    browser_get_page,
    browser_query,
    browser_scroll_to_text,
)
from src.tool_runtime.tools.brightness import set_brightness
from src.tool_runtime.tools.screenshot import screenshot
from src.tool_runtime.tools.scroll import scroll
from src.tool_runtime.tools.targets import click_target, propose_targets
from src.tool_runtime.tools.volume import set_volume
from src.tool_runtime.tools.spotify import (
    spotify_get_current_track,
    spotify_next,
    spotify_pause,
    spotify_play,
    spotify_previous,
    spotify_resume,
)

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
    "set_volume": set_volume,
    "set_brightness": set_brightness,
    "open_app": open_app,
    "browser_get_page": browser_get_page,
    "browser_extract_text": browser_extract_text,
    "browser_query": browser_query,
    "browser_scroll_to_text": browser_scroll_to_text,
    "browser_click_ref": browser_click_ref,
    "browser_fill_ref": browser_fill_ref,
    "propose_targets": propose_targets,
    "click_target": click_target,
    "spotify_play": spotify_play,
    "spotify_pause": spotify_pause,
    "spotify_resume": spotify_resume,
    "spotify_next": spotify_next,
    "spotify_previous": spotify_previous,
    "spotify_get_current_track": spotify_get_current_track,
}
