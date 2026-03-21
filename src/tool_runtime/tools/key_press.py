"""Keyboard shortcut tool for Playwright."""

from src.tool_runtime.tools.browser import get_manager

_KEY_MAP = {
    "cmd": "Meta",
    "ctrl": "Control",
    "alt": "Alt",
    "shift": "Shift",
    "enter": "Enter",
    "return": "Enter",
    "escape": "Escape",
    "esc": "Escape",
    "tab": "Tab",
    "space": "Space",
    "backspace": "Backspace",
    "delete": "Delete",
    "up": "ArrowUp",
    "down": "ArrowDown",
    "left": "ArrowLeft",
    "right": "ArrowRight",
    "home": "Home",
    "end": "End",
    "pageup": "PageUp",
    "pagedown": "PageDown",
    "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4",
    "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8",
    "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
}


def _to_playwright_key(key: str) -> str:
    """Convert human-readable key combos to Playwright format."""
    parts = key.split("+")
    mapped = []
    for part in parts:
        p = part.strip().lower()
        mapped.append(_KEY_MAP.get(p, part))
    return "+".join(mapped)


def key_press(key: str) -> dict:
    """Press a keyboard key or shortcut.

    Args:
        key: Key or combo separated by '+', e.g. "cmd+t", "escape", "enter".
             Use 'cmd' for Command on Mac (maps to Meta).
    """
    mgr = get_manager()
    pw_key = _to_playwright_key(key)

    async def _press():
        await mgr.page.keyboard.press(pw_key)
        return {"ok": True, "key": key, "playwright_key": pw_key}

    return mgr.run(_press())
