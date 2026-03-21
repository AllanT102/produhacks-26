"""Lightweight page metadata tool."""

from src.tool_runtime.tools.browser import get_manager


def get_page_info() -> dict:
    """Return the current page URL, title, and a text excerpt."""
    mgr = get_manager()

    async def _info():
        url = mgr.page.url
        title = await mgr.page.title()
        body_text = await mgr.page.evaluate("() => document.body?.innerText?.slice(0, 2000) ?? ''")
        return {"ok": True, "url": url, "title": title, "text": body_text}

    return mgr.run(_info())
