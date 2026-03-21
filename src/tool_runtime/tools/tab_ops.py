"""Browser tab management tools."""

from src.tool_runtime.tools.browser import get_manager


def open_tab(url: str | None = None) -> dict:
    """Open a new browser tab, optionally navigating to a URL."""
    mgr = get_manager()

    async def _open():
        page = await mgr.context.new_page()
        mgr._page = page
        if url:
            await page.goto(url, wait_until="domcontentloaded")
        return {"ok": True, "url": page.url}

    return mgr.run(_open())


def close_tab() -> dict:
    """Close the current tab and switch to the last remaining page."""
    mgr = get_manager()

    async def _close():
        pages = mgr.context.pages
        if len(pages) <= 1:
            return {"ok": False, "error": "Cannot close the last tab"}
        await mgr.page.close()
        mgr._page = mgr.context.pages[-1]
        return {"ok": True, "url": mgr._page.url}

    return mgr.run(_close())
