"""Scroll tool using small-step macOS pattern."""

import time

import pyautogui

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


def scroll(x: int, y: int, direction: str = "down", amount: int = 5) -> dict:
    """Scroll at (x, y) in small steps for macOS smoothness."""
    try:
        w, h = pyautogui.size()
        if not (0 <= x <= w and 0 <= y <= h):
            return {"ok": False, "error": f"Coordinates ({x}, {y}) out of screen bounds ({w}x{h})"}
        pyautogui.moveTo(x, y)
        step = -1 if direction == "down" else 1
        for _ in range(amount):
            pyautogui.scroll(step)
            time.sleep(0.02)
        return {"ok": True, "x": x, "y": y, "direction": direction, "amount": amount}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
