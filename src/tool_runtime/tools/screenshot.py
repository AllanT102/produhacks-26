"""Screenshot tool."""

import base64
import io


def screenshot() -> dict:
    """Capture the screen and return a base64-encoded PNG.

    The image is scaled to pyautogui's logical coordinate space so that pixel
    coordinates Claude reads from the image map 1:1 to what pyautogui expects.
    On Retina/HiDPI displays the raw capture is 2x; without this scaling Claude
    would produce coordinates that are off by a factor of 2.
    """
    try:
        import pyautogui
        from PIL import Image

        img = pyautogui.screenshot()
        logical_w, logical_h = pyautogui.size()
        if img.size != (logical_w, logical_h):
            img = img.resize((logical_w, logical_h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = base64.b64encode(buf.getvalue()).decode("utf-8")
        return {"ok": True, "data": data, "media_type": "image/png"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
