"""Print OCR results from the current screen."""
from src.tool_runtime.tools.screenshot import _run_ocr
import pyautogui, io
from PIL import Image

img = pyautogui.screenshot()
logical_w, logical_h = pyautogui.size()
if img.size != (logical_w, logical_h):
    img = img.resize((logical_w, logical_h), Image.LANCZOS)

buf = io.BytesIO()
img.save(buf, format="PNG")

regions = _run_ocr(buf.getvalue(), logical_w, logical_h)
print(f"{len(regions)} regions detected:\n")
for text, x, y, w, h in regions:
    cx, cy = x + w // 2, y + h // 2
    print(f"  ({cx:4d},{cy:4d})  {text!r}")
