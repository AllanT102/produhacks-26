"""Keyboard tools."""

import pyautogui

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


def type_text(text: str) -> dict:
    """Type a string of text at the current cursor position."""
    try:
        pyautogui.typewrite(text, interval=0.03)
        return {"ok": True, "text": text}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def key_press(key: str) -> dict:
    """Press a key or hotkey combination (e.g. 'enter', 'cmd+space', 'ctrl+c')."""
    try:
        if "+" in key:
            keys = [k.strip() for k in key.split("+")]
            pyautogui.hotkey(*keys)
        else:
            pyautogui.press(key)
        return {"ok": True, "key": key}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
