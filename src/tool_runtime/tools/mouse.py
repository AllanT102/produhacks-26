"""Mouse movement and drag tools."""

import pyautogui

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


def _validate(x: int, y: int) -> tuple:
    w, h = pyautogui.size()
    if not (0 <= x <= w and 0 <= y <= h):
        return False, f"Coordinates ({x}, {y}) out of screen bounds ({w}x{h})"
    return True, None


def move_to(x: int, y: int) -> dict:
    """Move the mouse cursor to (x, y) without clicking."""
    try:
        ok, err = _validate(x, y)
        if not ok:
            return {"ok": False, "error": err}
        pyautogui.moveTo(x, y)
        return {"ok": True, "x": x, "y": y}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def drag(start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5) -> dict:
    """Click and drag from (start_x, start_y) to (end_x, end_y)."""
    try:
        ok, err = _validate(start_x, start_y)
        if not ok:
            return {"ok": False, "error": err}
        ok, err = _validate(end_x, end_y)
        if not ok:
            return {"ok": False, "error": err}
        pyautogui.moveTo(start_x, start_y)
        pyautogui.dragTo(end_x, end_y, duration=duration, button="left")
        return {"ok": True, "start_x": start_x, "start_y": start_y, "end_x": end_x, "end_y": end_y}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
