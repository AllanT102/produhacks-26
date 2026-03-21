"""Claude tool JSON schemas for the Chrome browser action set.

Tool names must exactly match the keys in src/tool_runtime/tools/REGISTRY
so the planner can dispatch via execute_tool without any name mapping.
"""

TOOLS = [
    {
        "name": "screenshot",
        "description": (
            "Capture the current state of the Chrome browser viewport. "
            "Call this first to see what is on screen before deciding on the next action."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "navigate",
        "description": "Navigate to a URL or move through browser history.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Absolute URL to navigate to, e.g. 'https://google.com'",
                },
                "direction": {
                    "type": "string",
                    "enum": ["back", "forward"],
                    "description": "Go back or forward in browser history",
                },
            },
            "required": [],
        },
    },
    {
        "name": "find_elements",
        "description": (
            "Find DOM elements on the page matching a semantic query. "
            "Use this when click() is ambiguous — it returns element_ids you can pass to click()."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text, label, or description of the element to find",
                },
                "role": {
                    "type": "string",
                    "description": "Optional ARIA role to narrow the search, e.g. 'button', 'textbox', 'link'",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default 10)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "click",
        "description": (
            "Click a DOM element identified by description or element_id. "
            "Try description first; use find_elements + element_id when there are multiple matches."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Human-readable label, text, or placeholder of the element to click",
                },
                "element_id": {
                    "type": "string",
                    "description": "element_id from a prior find_elements call",
                },
                "role": {
                    "type": "string",
                    "description": "ARIA role to narrow the search, e.g. 'button', 'link'",
                },
                "index": {
                    "type": "integer",
                    "description": "0-based index when multiple matches exist (default 0)",
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "description": "Mouse button (default: left)",
                },
                "double": {
                    "type": "boolean",
                    "description": "True to double-click",
                },
            },
            "required": [],
        },
    },
    {
        "name": "type_text",
        "description": "Type text into an input field or at the current keyboard focus.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to type",
                },
                "description": {
                    "type": "string",
                    "description": "Label, placeholder, or name of the input field to type into",
                },
                "clear_first": {
                    "type": "boolean",
                    "description": "Replace existing value if True (default True)",
                },
                "press_enter": {
                    "type": "boolean",
                    "description": "Press Enter after typing (default False)",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "scroll",
        "description": "Scroll the page or scroll a specific element into view.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["up", "down", "left", "right"],
                    "description": "Scroll direction (default: down)",
                },
                "amount": {
                    "type": "integer",
                    "description": "Pixel distance to scroll (default 300)",
                },
                "description": {
                    "type": "string",
                    "description": "If provided, scroll this element into view instead of the page",
                },
            },
            "required": [],
        },
    },
    {
        "name": "key_press",
        "description": (
            "Press a keyboard key or shortcut combination. "
            "Use '+' to join modifiers, e.g. 'cmd+t', 'cmd+l', 'escape', 'enter'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Key or combo, e.g. 'enter', 'cmd+t', 'cmd+l', 'escape'",
                },
            },
            "required": ["key"],
        },
    },
    {
        "name": "get_page_info",
        "description": (
            "Return the current page URL, title, and a text excerpt. "
            "Use this as a lightweight alternative to screenshot when you only need metadata."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "open_tab",
        "description": "Open a new browser tab, optionally navigating to a URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to open in the new tab",
                },
            },
            "required": [],
        },
    },
    {
        "name": "close_tab",
        "description": "Close the current browser tab and switch to the last remaining page.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "set_volume",
        "description": "Adjust macOS system volume.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["up", "down", "mute", "unmute"],
                    "description": "Volume action to perform",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "set_brightness",
        "description": "Adjust macOS display brightness.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "Brightness direction",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "task_complete",
        "description": (
            "Signal that the user's goal has been fully achieved. "
            "Call this — and only this — when the task is done."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Brief description of what was accomplished",
                },
            },
            "required": ["summary"],
        },
    },
]
