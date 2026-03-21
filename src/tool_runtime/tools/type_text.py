"""Text input tool for Playwright."""

from src.tool_runtime.tools.browser import get_manager


async def _do_type(page, text: str, description: str | None, clear_first: bool, press_enter: bool):
    if description:
        strategies = [
            page.get_by_label(description),
            page.get_by_placeholder(description),
            page.get_by_role("textbox", name=description),
            page.get_by_role("searchbox", name=description),
            page.get_by_role("combobox", name=description),
        ]
        locator = None
        for strat in strategies:
            try:
                count = await strat.count()
            except Exception:
                continue
            if count > 0:
                locator = strat.first
                break

        if locator is None:
            return {"ok": False, "error": f"No input found for description={description!r}"}

        await locator.scroll_into_view_if_needed()
        if clear_first:
            await locator.fill(text)
        else:
            await locator.type(text)
    else:
        await page.keyboard.type(text)

    if press_enter:
        await page.keyboard.press("Enter")

    return {"ok": True, "text": text}


def type_text(
    text: str,
    description: str | None = None,
    clear_first: bool = True,
    press_enter: bool = False,
) -> dict:
    """Type text into an input field or at the current focus.

    Args:
        text: Text to type.
        description: Label, placeholder, or name of the input field to target.
        clear_first: If True, replace existing value (fill); otherwise append (type).
        press_enter: Press Enter after typing.
    """
    mgr = get_manager()
    return mgr.run(_do_type(mgr.page, text, description, clear_first, press_enter))
