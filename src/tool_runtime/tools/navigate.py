"""Browser navigation tool."""

from src.tool_runtime.tools.browser import get_manager


def navigate(url: str | None = None, direction: str | None = None) -> dict:
    """Navigate to a URL or go back/forward in history.

    Args:
        url: Absolute URL to navigate to.
        direction: "back" or "forward" to use browser history.
    """
    mgr = get_manager()

    async def _nav():
        if url:
            await mgr.page.goto(url, wait_until="domcontentloaded")
        elif direction == "back":
            await mgr.page.go_back()
        elif direction == "forward":
            await mgr.page.go_forward()
        else:
            return {"ok": False, "error": "Provide url or direction"}
        return {"ok": True, "url": mgr.page.url}

    return mgr.run(_nav())
