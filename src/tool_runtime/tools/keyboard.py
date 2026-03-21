"""Keyboard tools."""

import time

import pyautogui
import pyperclip

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


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


def type_text(text: str, clear_first: bool = False) -> dict:
    """Type text using clipboard paste, then press enter."""
    try:
        # Cant use .hotkey because of macos timing causing it to mistime the command and type the letter
        pyperclip.copy(text)
        if clear_first:
            pyautogui.keyDown("command")
            pyautogui.press("a")
            pyautogui.keyUp("command")
            time.sleep(0.1)
        time.sleep(0.1)
        pyautogui.keyDown("command")
        pyautogui.press("v")
        pyautogui.keyUp("command")
        time.sleep(0.1)
        pyautogui.press("enter")
        return {"ok": True, "text": text}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
