"""Click tools."""

import pyautogui

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


def _validate(x: int, y: int) -> tuple:
    w, h = pyautogui.size()
    if not (0 <= x <= w and 0 <= y <= h):
        return False, f"Coordinates ({x}, {y}) out of screen bounds ({w}x{h})"
    return True, None


def click(x: int, y: int, button: str = "left") -> dict:
    """Click at (x, y) with the given mouse button."""
    try:
        ok, err = _validate(x, y)
        if not ok:
            return {"ok": False, "error": err}
        pyautogui.click(x, y, button=button)
        return {"ok": True, "x": x, "y": y, "button": button}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def double_click(x: int, y: int) -> dict:
    """Double-click at (x, y)."""
    try:
        ok, err = _validate(x, y)
        if not ok:
            return {"ok": False, "error": err}
        pyautogui.doubleClick(x, y)
        return {"ok": True, "x": x, "y": y}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
