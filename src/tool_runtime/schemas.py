"""Claude tool JSON schemas for the desktop action set.

Tool names must exactly match the keys in src/tool_runtime/tools/REGISTRY
so the planner can dispatch via execute_tool without any name mapping.
"""

TOOLS = [
    {
        "name": "screenshot",
        "description": (
            "Capture the current state of the screen. Always call this first to see "
            "what is on screen before deciding on the next action."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "click",
        "description": "Click a mouse button at the specified screen coordinates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate in pixels"},
                "y": {"type": "integer", "description": "Y coordinate in pixels"},
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "description": "Mouse button to use (default: left)",
                },
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "propose_targets",
        "description": (
            "Find likely UI targets for a semantic query by merging local accessibility, OCR, "
            "and Dock/app-icon candidates. Prefer this before raw click coordinates when you "
            "need to click something visible on screen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What target to find, e.g. 'Slack icon', 'Directories folder', 'first file'",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of candidates to return",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "click_target",
        "description": "Click a previously proposed target by target_id instead of guessing coordinates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_id": {
                    "type": "string",
                    "description": "A target id returned from propose_targets",
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "description": "Mouse button to use (default: left)",
                },
                "click_count": {
                    "type": "integer",
                    "description": "1 for click, 2 for double-click",
                },
            },
            "required": ["target_id"],
        },
    },
    {
        "name": "double_click",
        "description": "Double-click at the specified screen coordinates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate in pixels"},
                "y": {"type": "integer", "description": "Y coordinate in pixels"},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "scroll",
        "description": "Scroll the content at the specified coordinates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate to scroll at"},
                "y": {"type": "integer", "description": "Y coordinate to scroll at"},
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "Scroll direction",
                },
                "amount": {
                    "type": "integer",
                    "description": "Number of scroll steps (default: 5)",
                },
            },
            "required": ["x", "y", "direction"],
        },
    },
    {
        "name": "type_text",
        "description": "Type a string of text at the current cursor position.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "key_press",
        "description": (
            "Press a keyboard key or hotkey combination. "
            "Use '+' to join modifier keys (e.g. 'cmd+space', 'ctrl+c', 'enter')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Key or hotkey combination (e.g. 'enter', 'cmd+tab', 'ctrl+c')",
                },
            },
            "required": ["key"],
        },
    },
    {
        "name": "move_to",
        "description": "Move the mouse cursor to the given coordinates without clicking.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate in pixels"},
                "y": {"type": "integer", "description": "Y coordinate in pixels"},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "drag",
        "description": "Click and drag from one position to another.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_x": {"type": "integer", "description": "Drag start X coordinate"},
                "start_y": {"type": "integer", "description": "Drag start Y coordinate"},
                "end_x": {"type": "integer", "description": "Drag end X coordinate"},
                "end_y": {"type": "integer", "description": "Drag end Y coordinate"},
                "duration": {
                    "type": "number",
                    "description": "Drag duration in seconds (default: 0.5)",
                },
            },
            "required": ["start_x", "start_y", "end_x", "end_y"],
        },
    },
    {
        "name": "open_app",
        "description": (
            "Open an application by name. Optionally provide a URL to open directly in that app, "
            "for example opening Google Chrome to https://youtube.com."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "app": {
                    "type": "string",
                    "description": "App name or alias such as 'chrome', 'slack', or 'finder'",
                },
                "url": {
                    "type": "string",
                    "description": "Optional URL to open in the app, such as 'https://youtube.com'",
                },
            },
            "required": ["app"],
        },
    },
    {
        "name": "browser_get_page",
        "description": "Get the URL and title of the active Google Chrome tab.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "browser_extract_text",
        "description": (
            "Extract readable text from the active Google Chrome tab for read-aloud and voice feedback. "
            "Supports page-level text, the current selection, the headline, or the first paragraph."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["page", "selection", "headline", "first_paragraph", "focus"],
                    "description": "Which part of the page to extract",
                },
                "fallback_scope": {
                    "type": "string",
                    "enum": ["", "page", "selection", "headline", "first_paragraph", "focus"],
                    "description": "Optional fallback scope if the requested scope is empty",
                },
                "max_blocks": {
                    "type": "integer",
                    "description": "Maximum number of content blocks to include when extracting page text",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum number of characters to return",
                },
            },
            "required": [],
        },
    },
    {
        "name": "browser_query",
        "description": (
            "Find semantic elements in the active Google Chrome tab by visible text, aria-label, "
            "placeholder, title, or role. Use this for webpage interactions before raw clicking."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What webpage element to find, such as 'Subscribe button' or 'Search input'",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of matches to return",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "browser_scroll_to_text",
        "description": (
            "Scroll the active Google Chrome tab until matching visible text is brought into view. "
            "Use this for commands like 'scroll to step 2', 'go to pricing', or 'jump to FAQ'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Visible page text to scroll to, such as 'Step 2' or 'Pricing'",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "browser_click_ref",
        "description": (
            "Click a previously returned browser element reference from browser_query. "
            "The ref must exactly match a ref returned earlier by browser_query; never invent or paraphrase it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "An exact DOM element ref returned by browser_query",
                },
            },
            "required": ["ref"],
        },
    },
    {
        "name": "browser_fill_ref",
        "description": (
            "Fill a previously returned browser element reference from browser_query with text. "
            "The ref must exactly match a ref returned earlier by browser_query; never invent or paraphrase it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "An exact DOM element ref returned by browser_query",
                },
                "text": {
                    "type": "string",
                    "description": "The text to type into the element",
                },
                "submit": {
                    "type": "boolean",
                    "description": "Whether to submit the field after filling it",
                },
            },
            "required": ["ref", "text"],
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
