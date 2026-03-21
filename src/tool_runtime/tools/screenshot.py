"""Playwright-based screenshot tool."""

import base64

from src.tool_runtime.tools.browser import get_manager


def screenshot() -> dict:
    mgr = get_manager()

    async def _capture():
        return await mgr.page.screenshot(type="png", full_page=False)

    data = mgr.run(_capture())
    return {
        "ok": True,
        "data": base64.b64encode(data).decode("ascii"),
        "media_type": "image/png",
    }
