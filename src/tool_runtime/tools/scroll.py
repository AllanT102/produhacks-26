"""Playwright-based scroll tool."""

from src.tool_runtime.tools.browser import get_manager


async def _do_scroll(page, direction: str, amount: int, description: str | None):
    if description:
        strategies = [
            page.get_by_text(description, exact=False),
            page.get_by_role("region", name=description),
        ]
        for strat in strategies:
            try:
                count = await strat.count()
            except Exception:
                continue
            if count > 0:
                await strat.first.scroll_into_view_if_needed()
                return {"ok": True, "scrolled_to": description}

    delta_x = 0
    delta_y = amount if direction == "down" else -amount
    if direction == "right":
        delta_x, delta_y = amount, 0
    elif direction == "left":
        delta_x, delta_y = -amount, 0

    await page.mouse.wheel(delta_x, delta_y)
    return {"ok": True, "direction": direction, "amount": amount}


def scroll(
    direction: str = "down",
    amount: int = 300,
    description: str | None = None,
) -> dict:
    """Scroll the page or scroll an element into view.

    Args:
        direction: "up", "down", "left", or "right".
        amount: Pixel distance to scroll (default 300).
        description: If provided, scroll this element into view instead.
    """
    mgr = get_manager()
    return mgr.run(_do_scroll(mgr.page, direction, amount, description))
