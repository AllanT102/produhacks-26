"""Screenshot tool."""

import base64
import io


def screenshot() -> dict:
    """Capture the screen and return a base64-encoded PNG."""
    try:
        import pyautogui
        from PIL import Image  # noqa: F401 — ensures Pillow is available

        img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = base64.b64encode(buf.getvalue()).decode("utf-8")
        return {"ok": True, "data": data, "media_type": "image/png"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
