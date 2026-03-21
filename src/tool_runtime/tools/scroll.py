"""Scroll tool."""

import pyautogui

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


def _validate(x: int, y: int) -> tuple:
    w, h = pyautogui.size()
    if not (0 <= x <= w and 0 <= y <= h):
        return False, f"Coordinates ({x}, {y}) out of screen bounds ({w}x{h})"
    return True, None


def scroll(x: int, y: int, direction: str = "down", amount: int = 5) -> dict:
    """Scroll at (x, y) by amount clicks."""
    try:
        ok, err = _validate(x, y)
        if not ok:
            return {"ok": False, "error": err}
        pyautogui.moveTo(x, y)
        clicks = -amount if direction == "down" else amount
        pyautogui.scroll(clicks)
        return {"ok": True, "x": x, "y": y, "direction": direction, "amount": amount}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
