"""DOM-aware click tool for Playwright."""

from src.tool_runtime.tools.browser import get_manager


def _build_locator(page, description: str | None, role: str | None):
    """Return the best locator given description and optional role."""
    if not description:
        return None

    strategies = []
    if role:
        strategies.append(page.get_by_role(role, name=description))
    strategies += [
        page.get_by_label(description),
        page.get_by_placeholder(description),
        page.get_by_role("button", name=description),
        page.get_by_role("link", name=description),
        page.get_by_role("textbox", name=description),
        page.get_by_role("combobox", name=description),
        page.get_by_text(description, exact=False),
        page.get_by_alt_text(description),
    ]
    return strategies


async def _do_click(page, description, role, element_id, index, button, double):
    from src.tool_runtime.tools.find_elements import _ELEMENT_CACHE

    locator = None

    # element_id from a previous find_elements call takes priority
    if element_id and element_id in _ELEMENT_CACHE:
        locator = _ELEMENT_CACHE[element_id]
    elif description:
        strategies = _build_locator(page, description, role)
        for strat in strategies:
            try:
                count = await strat.count()
            except Exception:
                continue
            if count > 0:
                locator = strat.nth(index)
                break

    if locator is None:
        return {"ok": False, "error": f"No element found for description={description!r} element_id={element_id!r}"}

    try:
        await locator.scroll_into_view_if_needed()
        if double:
            await locator.dblclick(button=button)
        else:
            await locator.click(button=button)
        return {"ok": True, "description": description, "element_id": element_id, "button": button}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def click(
    description: str | None = None,
    element_id: str | None = None,
    role: str | None = None,
    index: int = 0,
    button: str = "left",
    double: bool = False,
) -> dict:
    """Click a DOM element.

    Args:
        description: Human-readable label, text, or placeholder of the element.
        element_id: ID from a prior find_elements call (takes priority over description).
        role: ARIA role to narrow the search (e.g. "button", "link", "textbox").
        index: 0-based index when multiple matches exist.
        button: "left", "right", or "middle".
        double: True for a double-click.
    """
    mgr = get_manager()
    return mgr.run(_do_click(mgr.page, description, role, element_id, index, button, double))
