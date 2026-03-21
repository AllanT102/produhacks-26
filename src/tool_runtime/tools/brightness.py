"""Brightness tool."""

import subprocess


# macOS key codes for brightness keys
_KEY_UP = 144
_KEY_DOWN = 145


def set_brightness(action: str, steps: int = 1) -> dict:
    """
    Adjust display brightness.

    Args:
        action: "up" or "down"
        steps:  Number of increments to raise/lower.
    """
    if action not in ("up", "down"):
        return {"ok": False, "error": f"action must be 'up' or 'down', got '{action}'"}

    key_code = _KEY_UP if action == "up" else _KEY_DOWN

    try:
        for _ in range(steps):
            subprocess.run(
                ["osascript", "-e", f'tell application "System Events" to key code {key_code}'],
                check=True,
            )
        return {"ok": True, "action": action, "steps": steps}

    except Exception as exc:
        return {"ok": False, "error": str(exc)}
