"""DOM element finder tool — shared element cache for click by id."""

import uuid
from typing import Any

from src.tool_runtime.tools.browser import get_manager

# Shared cache: element_id -> playwright Locator (accessed on browser thread only)
_ELEMENT_CACHE: dict[str, Any] = {}


def _clear_cache():
    _ELEMENT_CACHE.clear()


async def _collect_elements(page, query: str, role: str | None, limit: int) -> list[dict]:
    """Try multiple locator strategies and return up to limit unique elements."""
    locators = []

    if role:
        locators.append(page.get_by_role(role, name=query))
        locators.append(page.get_by_role(role))
    else:
        locators.append(page.get_by_role("button", name=query))
        locators.append(page.get_by_role("link", name=query))
        locators.append(page.get_by_role("textbox", name=query))
        locators.append(page.get_by_role("combobox", name=query))
        locators.append(page.get_by_role("searchbox", name=query))

    locators.append(page.get_by_label(query))
    locators.append(page.get_by_placeholder(query))
    locators.append(page.get_by_text(query, exact=False))
    locators.append(page.get_by_alt_text(query))

    results = []
    seen_texts: set[str] = set()

    for loc in locators:
        if len(results) >= limit:
            break
        try:
            count = await loc.count()
        except Exception:
            continue

        for i in range(min(count, limit - len(results))):
            try:
                nth = loc.nth(i)
                text = (await nth.inner_text()).strip()[:120]
                tag = await nth.evaluate("el => el.tagName.toLowerCase()")
                aria_role = await nth.get_attribute("role") or ""
            except Exception:
                continue

            key = f"{tag}:{text}"
            if key in seen_texts:
                continue
            seen_texts.add(key)

            eid = str(uuid.uuid4())[:8]
            _ELEMENT_CACHE[eid] = nth
            results.append({"element_id": eid, "text": text, "tag": tag, "role": aria_role})

    return results


def find_elements(query: str, role: str | None = None, limit: int = 10) -> dict:
    """Find DOM elements matching a semantic query.

    Args:
        query: Text, label, or description of the element to find.
        role: Optional ARIA role to narrow the search (e.g. "button", "textbox").
        limit: Maximum number of results (default 10).
    """
    mgr = get_manager()
    _clear_cache()

    results = mgr.run(_collect_elements(mgr.page, query, role, limit))
    return {"ok": True, "elements": results}
