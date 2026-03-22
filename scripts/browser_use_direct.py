#!/usr/bin/env python3
"""Deterministic browser-use helper for fast browser actions.

Run this with the Python interpreter from `.venv-browseruse`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus, urlparse

from browser_use import Agent, Browser
from browser_use.llm.anthropic.chat import ChatAnthropic

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SYSTEM_PROMPT_PATH = _REPO_ROOT / "src" / "agent" / "system_prompt.md"
_DEFAULT_SYSTEM_PROMPT = """You are a browser control agent focused on fast, reliable web actions.

[user prompt]

Rules:
- Prefer the fewest steps needed to finish the user's request.
- Reuse the current browser tab/session when possible.
- Do not open extra pages or tabs unless required.
- If the goal is already achieved, finish immediately.
- Return a short final_result describing what you did and where you ended up.
"""


@dataclass
class CommandIntent:
    url: Optional[str] = None
    open_in_new_tab: bool = False
    search_query: Optional[str] = None
    search_provider: Optional[str] = None
    scroll_text: Optional[str] = None
    scroll_direction: Optional[str] = None
    scroll_amount: int = 0
    click_text: Optional[str] = None
    click_kind_hint: Optional[str] = None
    open_first_video: bool = False
    route: Optional[str] = None
    click_first_kind: Optional[str] = None
    click_first_query: Optional[str] = None
    profile_query: Optional[str] = None
    video_query: Optional[str] = None
    tab_index: Optional[int] = None


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_browser_command(command: str) -> str:
    """Trim filler language so more spoken commands hit the direct browser path."""
    text = _normalize_whitespace(command).strip()
    text = re.sub(r"^[\-\u2013\u2014•*]+\s*", "", text)
    text = re.sub(r"[.!?]+$", "", text).strip()
    text = re.sub(r"^(?:oh|uh|um|ah|so|well|and|then)\b[\s,.-]*", "", text, flags=re.IGNORECASE)

    prefixes = (
        "hi, ",
        "hi ",
        "please ",
        "hey ",
        "okay ",
        "ok ",
        "can you ",
        "could you ",
        "would you ",
        "will you ",
        "can u ",
        "i want you to ",
        "i need you to ",
    )
    changed = True
    while changed:
        changed = False
        lower = text.lower()
        for prefix in prefixes:
            if lower.startswith(prefix):
                text = text[len(prefix):].strip()
                changed = True
                break

    while text.lower().startswith("just "):
        text = text[5:].strip()

    if re.match(
        r"^you\s+(?:open|go|search|find|look|click|scroll|read|check|show|press|close|play|pause|message|reply|send|type|write)\b",
        text,
        flags=re.IGNORECASE,
    ):
        text = re.sub(r"^you\s+", "", text, count=1, flags=re.IGNORECASE).strip()

    replacements = (
        (r"^check my messages$", "open messages"),
        (r"^open my messages$", "open messages"),
        (r"^click messaging$", "open messages"),
        (r"^open messaging$", "open messages"),
        (r"^check my notifications$", "open notifications"),
        (r"^open my notifications$", "open notifications"),
        (r"^click notifications$", "open notifications"),
        (r"^show my notifications$", "open notifications"),
        (r"^go to my network$", "open my network"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return _normalize_whitespace(text).strip()


def _clean_search_query(value: str) -> str:
    query = _normalize_whitespace(value).strip(" .")
    query = re.sub(
        r"\s+(?:on\s+(?:youtube(?:\s+music)?|linkedin|google)|and\s+(?:play|open|click|subscribe|pause|scroll).*)$",
        "",
        query,
        flags=re.IGNORECASE,
    )
    return query.strip(" .")


def _extract_search_provider(text: str) -> Optional[str]:
    lowered = _normalize_whitespace(text).lower()
    match = re.search(r"\bon\s+(youtube(?:\s+music)?|linkedin|google)\b", lowered)
    if match:
        provider = match.group(1)
        if provider == "youtube music":
            return "youtube_music"
        return provider
    if lowered.startswith("look up "):
        return "google"
    return None


def _extract_generic_click_target(text: str) -> tuple[Optional[str], Optional[str]]:
    match = re.match(
        r"^(?:click|tap|press|select|choose)(?:\s+on)?\s+(?P<label>.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None, None

    label = _normalize_whitespace(match.group("label")).strip(" .")
    label = re.sub(r"^(?:the|a|an)\s+", "", label, flags=re.IGNORECASE)
    kind_match = re.search(r"\s+(button|link|tab|item|icon|option)\s*$", label, flags=re.IGNORECASE)
    click_kind_hint = kind_match.group(1).lower() if kind_match else None
    label = re.sub(r"\s+(?:button|link|tab|item|icon|option)\s*$", "", label, flags=re.IGNORECASE)
    label = _normalize_whitespace(label).strip(" .")
    lower = label.lower()

    if not label:
        return None, None
    if any(token in lower for token in (" first ", " second ", " third ", " last ")):
        return None, None
    if lower.startswith(("first ", "second ", "third ", "last ")):
        return None, None
    if any(pronoun in lower for pronoun in (" his ", " her ", " their ")):
        return None, None
    if lower in {"his profile", "her profile", "their profile"}:
        return None, None
    max_words = 10 if click_kind_hint in {"link", "button", "tab"} else 8
    if len(label.split()) > max_words:
        return None, None
    if click_kind_hint is None and lower in {"x", "close", "dismiss"}:
        click_kind_hint = "button"
    return label, click_kind_hint


def _site_alias_url(target: str) -> Optional[str]:
    normalized = _normalize_whitespace(target).lower()
    known_urls = {
        "google": "https://www.google.com",
        "google search": "https://www.google.com",
        "youtube": "https://www.youtube.com",
        "youtube music": "https://music.youtube.com",
        "linkedin": "https://www.linkedin.com/feed/",
        "twitter": "https://x.com/home",
        "x": "https://x.com/home",
        "gmail": "https://mail.google.com",
        "github": "https://github.com",
        "google maps": "https://maps.google.com",
        "google docs": "https://docs.google.com",
        "google drive": "https://drive.google.com",
        "google calendar": "https://calendar.google.com",
    }
    return known_urls.get(normalized)


def _guess_site_url_from_target(target: str) -> Optional[str]:
    alias_url = _site_alias_url(target)
    if alias_url:
        return alias_url

    host = _normalize_whitespace(target).lower()
    if host in {"chrome", "browser", "messages", "notifications", "my network"}:
        return None
    if " " in host:
        return None
    if "." in host:
        return f"https://{host}"
    return f"https://www.{host}.com"


def _guess_open_site_url(text: str) -> Optional[str]:
    match = re.match(
        r"^(?:open|go to|navigate to|show)\s+(.+?)$",
        text.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return _guess_site_url_from_target(match.group(1))


def _is_enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _direct_search_url(search_provider: Optional[str], search_query: Optional[str]) -> Optional[str]:
    if not search_query:
        return None
    if search_provider == "youtube":
        return f"https://www.youtube.com/results?search_query={quote_plus(search_query)}"
    if search_provider == "youtube_music":
        return f"https://music.youtube.com/search?q={quote_plus(search_query)}"
    if search_provider == "linkedin":
        return f"https://www.linkedin.com/search/results/all/?keywords={quote_plus(search_query)}&origin=GLOBAL_SEARCH_HEADER"
    if search_provider == "google":
        return f"https://www.google.com/search?q={quote_plus(search_query)}"
    return None


def parse_intent(command: str) -> CommandIntent:
    text = normalize_browser_command(command)
    lower = text.lower()

    open_in_new_tab = False
    search_query = None
    click_kind_hint = None
    new_tab_match = re.match(
        r"^(?:open|start)\s+a new tab(?:\s+(?:with|for))?\s+(.+?)$",
        text,
        flags=re.IGNORECASE,
    )
    if new_tab_match:
        target_url = _guess_site_url_from_target(new_tab_match.group(1))
        if target_url:
            open_in_new_tab = True
            text = f"open {new_tab_match.group(1)}"
            lower = text.lower()

    search_provider = None
    search_patterns = [
        r"\bsearch up (?P<q>.+?)(?:,| then | and (?:open|click|subscribe|pause|scroll|play)\b|$)",
        r"\bsearch for (?P<q>.+?)(?:,| then | and (?:open|click|subscribe|pause|scroll)\b|$)",
        r"\bsearch (?P<q>.+?)(?:,| then | and (?:open|click|subscribe|pause|scroll)\b|$)",
        r"\blook up (?P<q>.+?)(?:,| then | and (?:open|click|subscribe|pause|scroll)\b|$)",
    ]
    for pattern in search_patterns:
        match = re.search(pattern, lower, flags=re.IGNORECASE)
        if match:
            search_provider = _extract_search_provider(text)
            search_query = _clean_search_query(text[match.start("q"):match.end("q")])
            break

    url_match = re.search(r"https?://\S+", text)
    if url_match:
        url = url_match.group(0).rstrip(".,)")
    else:
        url = _direct_search_url(search_provider, search_query)
        if url is not None:
            search_query = None
        else:
            url = _guess_open_site_url(text)

    scroll_text = None
    scroll_match = re.search(r"\bscroll to (?P<t>.+?)(?:,| then | and |$)", lower, flags=re.IGNORECASE)
    if scroll_match:
        scroll_text = _normalize_whitespace(text[scroll_match.start("t"):scroll_match.end("t")]).strip(" .")
    if scroll_text is None:
        go_down_match = re.search(
            r"\bgo down to (?P<t>.+?)(?:,| then | and |$)",
            lower,
            flags=re.IGNORECASE,
        )
        if go_down_match:
            scroll_text = _normalize_whitespace(text[go_down_match.start("t"):go_down_match.end("t")]).strip(" .")
    if scroll_text is None:
        find_match = re.match(r"^(?:find|locate)\s+(?P<t>.+?)$", text, flags=re.IGNORECASE)
        if find_match:
            scroll_text = _normalize_whitespace(find_match.group("t")).strip(" .")

    click_text = None
    if "subscribe" in lower:
        click_text = "Subscribe"
        click_kind_hint = "button"
    elif lower in {"click on view profile", "click view profile", "view profile", "click on my profile", "open my profile"}:
        click_text = "View profile"
        click_kind_hint = "link"

    route = None
    if lower in {"open messages", "go to messages"}:
        route = "messages"
    elif lower in {"open notifications", "go to notifications"}:
        route = "notifications"
    elif lower in {"open my network", "go to my network"}:
        route = "network"
    elif lower in {"open chrome", "open browser", "open google chrome"}:
        route = "browser"
    elif lower in {"back", "go back", "go back a page", "go back one page"}:
        route = "back"
    elif lower in {"forward", "go forward", "go forward a page", "go forward one page"}:
        route = "forward"
    elif lower in {"reload", "refresh", "reload page", "refresh page"}:
        route = "reload"
    elif lower in {"hard reload", "hard refresh"}:
        route = "hard_reload"
    elif lower in {"new tab", "open new tab"}:
        route = "new_tab"
    elif lower in {"close tab", "close the tab", "close this tab", "close current tab"}:
        route = "close_tab"
    elif lower in {"reopen closed tab", "undo close tab"}:
        route = "reopen_tab"
    elif lower in {"next tab", "go to next tab", "switch to next tab"}:
        route = "next_tab"
    elif lower in {"previous tab", "prev tab", "go to previous tab", "switch to previous tab"}:
        route = "previous_tab"
    elif lower in {"focus address bar", "focus url bar", "focus search bar", "address bar"}:
        route = "address_bar"
    elif lower in {"scroll to top", "go to top", "top of page"}:
        route = "scroll_top"
    elif lower in {"scroll to bottom", "go to bottom", "bottom of page"}:
        route = "scroll_bottom"

    if route in {"scroll_top", "scroll_bottom"}:
        scroll_text = None
    elif lower in {"mute", "mute it", "unmute", "unmute it"}:
        route = "mute_toggle"
    elif lower in {"fullscreen", "go fullscreen", "enter fullscreen", "exit fullscreen"}:
        route = "fullscreen_toggle"
    elif lower in {"skip ahead ten seconds", "skip forward ten seconds", "forward ten seconds"}:
        route = "seek_forward"
    elif lower in {"skip back ten seconds", "go back ten seconds", "rewind ten seconds"}:
        route = "seek_backward"

    click_first_kind = None
    click_first_query = None
    first_target_match = re.search(
        r"\b(?:click|open)(?: on)? the first (?:(?P<query>.+?) )?(?P<kind>link|result|profile|video|tab)\b",
        lower,
        flags=re.IGNORECASE,
    )
    if first_target_match:
        click_first_kind = first_target_match.group("kind")
        query_value = first_target_match.group("query") or ""
        click_first_query = _normalize_whitespace(query_value).strip(" .") or None

    if click_first_kind is None:
        any_target_match = re.search(
            r"\b(?:click|open)(?: on)? (?:one|any) of the (?P<query>.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if any_target_match:
            click_first_kind = "link"
            click_first_query = _normalize_whitespace(any_target_match.group("query")).strip(" .")

    video_query = None
    video_match = re.search(
        r"\b(?:click|open|play)(?: on)? (?:the )?(?:video by )(?P<query>.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if not video_match:
        video_match = re.search(
            r"\b(?:click|open|play)(?: on)? (?:the )?(?P<query>.+?) (?:music )?video\b",
            text,
            flags=re.IGNORECASE,
        )
    if video_match:
        video_query = _normalize_whitespace(video_match.group("query")).strip(" .")

    profile_query = None
    profile_match = re.search(
        r"\b(?:click|open)(?: on)? (?P<query>.+?)'s profile\b",
        text,
        flags=re.IGNORECASE,
    )
    if profile_match:
        profile_query = _normalize_whitespace(profile_match.group("query")).strip(" .")

    scroll_direction = None
    scroll_amount = 0
    if lower.startswith("scroll") and scroll_text is None:
        scroll_direction = "up" if "up" in lower else "down"
        scroll_amount = 620
        if any(token in lower for token in ("little", "a bit", "slightly")):
            scroll_amount = 320
        elif any(token in lower for token in ("more", "further", "fast", "faster", "lot", "way")):
            scroll_amount = 960
    if route in {"scroll_top", "scroll_bottom"}:
        scroll_direction = None
        scroll_amount = 0

    open_first_video = "youtube" in lower and any(
        phrase in lower
        for phrase in (
            "play the video",
            "play video",
            "play the first result",
            "open the first result",
            "play the first video",
            "open the video",
        )
    )

    if lower in {"play", "play it", "pause", "pause it", "resume", "resume it"}:
        route = "playback_toggle"

    tab_index = None
    tab_match = re.match(r"^(?:go to|switch to|open)\s+tab\s+([1-8])$", lower)
    if tab_match:
        tab_index = int(tab_match.group(1))

    if (
        click_text is None
        and route is None
        and click_first_kind is None
        and profile_query is None
        and video_query is None
        and search_query is None
        and url is None
    ):
        click_text, click_kind_hint = _extract_generic_click_target(text)

    return CommandIntent(
        url=url,
        open_in_new_tab=open_in_new_tab,
        search_query=search_query,
        search_provider=search_provider,
        scroll_text=scroll_text,
        scroll_direction=scroll_direction,
        scroll_amount=scroll_amount,
        click_text=click_text,
        click_kind_hint=click_kind_hint,
        open_first_video=open_first_video,
        route=route,
        click_first_kind=click_first_kind,
        click_first_query=click_first_query,
        profile_query=profile_query,
        video_query=video_query,
        tab_index=tab_index,
    )


def _line_score(line: str, query: str, preferred_tags: tuple[str, ...], preferred_terms: tuple[str, ...]) -> int:
    score = 0
    hay = line.lower()
    q = query.lower().strip()
    tokens = [token for token in re.split(r"\s+", q) if token]
    if q and q in hay:
        score += 30
    for token in tokens:
        if token in hay:
            score += 6
    if any(tag in hay for tag in preferred_tags):
        score += 10
    if any(term in hay for term in preferred_terms):
        score += 8
    return score


def _extract_blocks(state_text: str) -> list[dict]:
    blocks: list[dict] = []
    current: Optional[dict] = None
    for raw_line in state_text.splitlines():
        line = raw_line.rstrip()
        match = re.match(r"(?:\|SHADOW\(open\)\|)?\[(\d+)\](.*)$", line.strip())
        if match:
            current = {
                "index": int(match.group(1)),
                "header": match.group(2).strip(),
                "lines": [match.group(2).strip()],
            }
            blocks.append(current)
            continue
        if current is not None and line.strip():
            current["lines"].append(line.strip())
    for block in blocks:
        block["text"] = "\n".join([part for part in block["lines"] if part]).strip()
    return blocks


def find_best_index(
    state_text: str,
    query: str,
    preferred_tags: tuple[str, ...] = (),
    preferred_terms: tuple[str, ...] = (),
) -> Optional[int]:
    best_index: Optional[int] = None
    best_score = 0
    for block in _extract_blocks(state_text):
        line = block["text"]
        score = _line_score(line, query, preferred_tags, preferred_terms)
        if score > best_score:
            best_score = score
            best_index = block["index"]
    return best_index


async def _scroll_container(
    page,
    *,
    direction: Optional[str] = None,
    amount: int = 0,
    mode: str = "relative",
) -> dict:
    signed_amount = 0
    if direction is not None:
        signed_amount = -abs(amount) if direction == "up" else abs(amount)

    result_text = await page.evaluate(
        """(payload) => {
            const mode = String(payload.mode || 'relative');
            const amount = Number(payload.amount || 0);
            const isVisible = (el) => {
              if (!el) return false;
              const rect = el.getBoundingClientRect();
              const style = window.getComputedStyle(el);
              return rect.width > 0
                && rect.height > 0
                && style.visibility !== 'hidden'
                && style.display !== 'none';
            };
            const isScrollable = (el) => {
              if (!el || el === document.body) return false;
              const style = window.getComputedStyle(el);
              const overflowY = style.overflowY || '';
              const canScroll = /(auto|scroll|overlay)/i.test(overflowY);
              return el.scrollHeight > el.clientHeight + 8 && canScroll;
            };
            const candidateScore = (el) => {
              if (!isVisible(el)) return -1;
              const rect = el.getBoundingClientRect();
              const scrollRange = el.scrollHeight - el.clientHeight;
              return scrollRange + Math.min(rect.width * rect.height, 2_000_000) / 1000;
            };
            const collectAncestors = (start, acc) => {
              let node = start;
              while (node && node !== document.body && node !== document.documentElement) {
                if (node instanceof HTMLElement) acc.push(node);
                node = node.parentElement;
              }
            };

            const candidates = [];
            const add = (el) => {
              if (!el || candidates.includes(el)) return;
              candidates.push(el);
            };

            collectAncestors(document.activeElement, candidates);
            collectAncestors(document.elementFromPoint(window.innerWidth / 2, window.innerHeight / 2), candidates);
            collectAncestors(document.querySelector('main'), candidates);

            const scrollables = Array.from(document.querySelectorAll('*'))
              .filter((el) => el instanceof HTMLElement && isScrollable(el))
              .sort((a, b) => candidateScore(b) - candidateScore(a));
            for (const el of scrollables.slice(0, 25)) add(el);

            const root = document.scrollingElement || document.documentElement;
            add(root);

            let target = candidates.find((el) => isScrollable(el)) || root;
            if (!target) target = root;

            const before = target === root ? window.scrollY : target.scrollTop;

            if (mode === 'inspect') {
              // no-op, just measure current scroll position
            } else if (mode === 'top') {
              if (target === root) {
                window.scrollTo({top: 0, left: 0, behavior: 'instant'});
              } else {
                target.scrollTo({top: 0, left: 0, behavior: 'instant'});
              }
            } else if (mode === 'bottom') {
              if (target === root) {
                window.scrollTo({top: root.scrollHeight, left: 0, behavior: 'instant'});
              } else {
                target.scrollTo({top: target.scrollHeight, left: 0, behavior: 'instant'});
              }
            } else if (target === root) {
              window.scrollBy({top: amount, left: 0, behavior: 'instant'});
            } else {
              target.scrollBy({top: amount, left: 0, behavior: 'instant'});
            }

            const after = target === root ? window.scrollY : target.scrollTop;
            const changed = Math.abs(after - before) >= 4;
            const rect = target.getBoundingClientRect ? target.getBoundingClientRect() : {x: 0, y: 0, width: 0, height: 0};
            return JSON.stringify({
              ok: true,
              changed,
              before: Math.round(before),
              after: Math.round(after),
              target: target === root ? 'document' : (target.tagName || 'unknown').toLowerCase(),
              id: target.id || '',
              className: typeof target.className === 'string' ? target.className.slice(0, 120) : '',
              bbox: {
                x: Math.round(rect.left || 0),
                y: Math.round(rect.top || 0),
                width: Math.round(rect.width || 0),
                height: Math.round(rect.height || 0),
              },
              href: window.location.href,
              title: document.title
            });
        }""",
        {"amount": signed_amount, "mode": mode},
    )
    result = json.loads(result_text or "{}")
    if not result.get("ok"):
        raise RuntimeError("Could not scroll the current page.")
    return result


async def _open_url(browser: Browser, url: str) -> None:
    target = url.lower()
    for attempt in range(2):
        try:
            await browser.navigate_to(url)
            await asyncio.sleep(0.35)
            return
        except Exception as exc:
            message = str(exc)
            if "ERR_ABORTED" not in message and attempt == 1:
                raise
            await asyncio.sleep(0.25)
            try:
                state = await browser.get_browser_state_summary(include_screenshot=False)
            except Exception:
                state = None
            current_url = str(getattr(state, "url", "") or "").lower()
            if current_url and (current_url.startswith(target) or urlparse(target).netloc in current_url):
                return
            if attempt == 1:
                raise


async def _fill_search(browser: Browser, query: str) -> dict:
    state = await browser.get_browser_state_summary(include_screenshot=False)
    state_text = state.dom_state.llm_representation()
    search_index = find_best_index(
        state_text,
        "search",
        preferred_tags=("<input", "role=combobox", "role=searchbox"),
        preferred_terms=("aria-label=search", "placeholder=search"),
    )
    if search_index is None:
        raise RuntimeError("Could not find a search input in the browser state.")

    node = await browser.get_element_by_index(search_index)
    if node is None:
        raise RuntimeError(f"Search input index {search_index} disappeared.")
    page = await browser.must_get_current_page()
    element = await page.get_element(node.backend_node_id)
    await element.fill(query, clear=True)
    await page.press("Enter")
    await asyncio.sleep(0.45)

    state = await browser.get_browser_state_summary(include_screenshot=False)
    return {
        "search_index": search_index,
        "url": state.url,
        "title": state.title,
    }


async def _open_first_youtube_video(browser: Browser) -> dict:
    page = await browser.must_get_current_page()
    result_text = await page.evaluate(
        """() => {
            const links = Array.from(document.querySelectorAll('a#video-title, a[href*="/watch"]'));
            const visible = links.find((el) => {
              const rect = el.getBoundingClientRect();
              const style = window.getComputedStyle(el);
              const href = el.getAttribute('href') || '';
              return href.includes('/watch')
                && rect.width > 0
                && rect.height > 0
                && style.visibility !== 'hidden'
                && style.display !== 'none';
            });
            if (!visible) {
              return JSON.stringify({ok:false,error:'Could not find a visible YouTube video result.'});
            }
            const label = (visible.innerText || visible.textContent || '').trim();
            visible.click();
            return JSON.stringify({ok:true,label,href:visible.href || visible.getAttribute('href') || ''});
        }"""
    )
    result = json.loads(result_text or "{}")
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "Could not open the first YouTube video result.")
    await asyncio.sleep(0.7)

    state = await browser.get_browser_state_summary(include_screenshot=False)
    return {
        "label": result.get("label") or "First YouTube result",
        "href": result.get("href"),
        "url": state.url,
        "title": state.title,
    }


async def _click_video_candidate(browser: Browser, query: str) -> dict:
    page = await browser.must_get_current_page()
    result_text = await page.evaluate(
        """(query) => {
            const q = String(query || '').trim().toLowerCase();
            const tokens = q.split(/\\s+/).filter(Boolean);
            const containers = Array.from(
              document.querySelectorAll(
                'ytd-rich-item-renderer,ytd-video-renderer,ytd-grid-video-renderer,ytd-compact-video-renderer'
              )
            );
            const isVisible = (el) => {
              const rect = el.getBoundingClientRect();
              const style = window.getComputedStyle(el);
              return rect.width > 0
                && rect.height > 0
                && style.visibility !== 'hidden'
                && style.display !== 'none';
            };
            const score = (text) => {
              const hay = String(text || '').toLowerCase();
              if (!hay) return 0;
              let total = 0;
              if (q && hay.includes(q)) total += 20;
              for (const token of tokens) {
                if (hay.includes(token)) total += 5;
              }
              return total;
            };

            let best = null;
            for (const container of containers) {
              if (!isVisible(container)) continue;
              const link = container.querySelector('a#video-title, a[href*="/watch"]');
              if (!link || !isVisible(link)) continue;
              const fullText = (container.innerText || container.textContent || '').trim();
              const s = score(fullText);
              if (s <= 0) continue;
              if (!best || s > best.score) {
                best = {
                  link,
                  score: s,
                  label: (link.innerText || link.textContent || '').trim(),
                  href: link.href || link.getAttribute('href') || '',
                };
              }
            }

            if (!best) {
              const fallbackLinks = Array.from(document.querySelectorAll('a#video-title, a[href*="/watch"]'))
                .filter((el) => isVisible(el))
                .map((el) => ({
                  el,
                  label: (el.innerText || el.textContent || '').trim(),
                  href: el.href || el.getAttribute('href') || '',
                  score: score((el.innerText || el.textContent || '').trim()),
                }))
                .filter((entry) => entry.score > 0)
                .sort((a, b) => b.score - a.score);
              if (fallbackLinks.length) {
                best = {
                  link: fallbackLinks[0].el,
                  label: fallbackLinks[0].label,
                  href: fallbackLinks[0].href,
                  score: fallbackLinks[0].score,
                };
              }
            }

            if (!best) {
              return JSON.stringify({ok:false,error:`No matching visible video found for "${query}".`});
            }

            best.link.click();
            return JSON.stringify({ok:true,label: best.label, href: best.href});
        }""",
        query,
    )
    result = json.loads(result_text or "{}")
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or f"Could not click video for '{query}'.")
    await asyncio.sleep(0.6)
    state = await browser.get_browser_state_summary(include_screenshot=False)
    return {
        "query": query,
        "label": result.get("label") or "Matched video",
        "href": result.get("href"),
        "url": state.url,
        "title": state.title,
    }


async def _scroll_to_text(browser: Browser, target: str) -> dict:
    page = await browser.must_get_current_page()
    result_text = await page.evaluate(
        """(target) => {
            const q = String(target || '').trim().toLowerCase();
            const tokens = q.split(/\\s+/).filter(Boolean);
            const tokenMatch = (hay, token) => {
              if (!hay || !token) return false;
              if (/^[a-z0-9]{1,2}$/i.test(token)) {
                const escaped = token.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
                return new RegExp(`(^|\\\\b)${escaped}(\\\\b|$)`, 'i').test(hay);
              }
              return hay.includes(token);
            };
            const selector = 'h1,h2,h3,h4,h5,h6,p,li,span,a,button,label,summary,dt,dd,div';
            const isVisible = (el) => {
              const rect = el.getBoundingClientRect();
              const style = window.getComputedStyle(el);
              return style.visibility !== 'hidden' && style.display !== 'none';
            };
            const score = (text, tag) => {
              const hay = String(text || '').toLowerCase().trim();
              if (!hay) return 0;
              const matchedTokens = tokens.filter((token) => tokenMatch(hay, token));
              if (!hay.includes(q)) {
                if (tokens.length >= 2 && matchedTokens.length < tokens.length) return 0;
                if (tokens.length === 1 && matchedTokens.length === 0) return 0;
              }
              let total = 0;
              if (hay === q) total += 60;
              if (hay.includes(q)) total += 30;
              for (const token of tokens) {
                if (tokenMatch(hay, token)) total += 8;
              }
              if (/^h[1-6]$/i.test(tag || '')) total += 6;
              return total;
            };
            let best = null;
            for (const el of Array.from(document.querySelectorAll(selector))) {
              if (!isVisible(el)) continue;
              const text = (el.innerText || el.textContent || '').trim();
              const s = score(text, el.tagName);
              if (s <= 0) continue;
              if (!best || s > best.score) best = {el, text, score: s, tag: el.tagName.toLowerCase()};
            }
            if (!best) return JSON.stringify({ok:false,error:`No visible text match found for "${target}"`});
            best.el.scrollIntoView({block:'center', inline:'nearest', behavior:'instant'});
            const rect = best.el.getBoundingClientRect();
            return JSON.stringify({
              ok:true,
              text: target,
              label: best.text,
              tag: best.tag,
              bbox:{x:Math.round(rect.left), y:Math.round(rect.top), width:Math.round(rect.width), height:Math.round(rect.height)},
              url: window.location.href,
              title: document.title
            });
        }""",
        target,
    )
    result = json.loads(result_text or "{}")
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or f"Could not scroll to '{target}'")
    return result


async def _click_text(browser: Browser, text: str, kind_hint: Optional[str] = None) -> dict:
    before_state = await browser.get_browser_state_summary(include_screenshot=False)
    before_url = str(before_state.url or "")
    before_title = str(before_state.title or "")
    page = await browser.must_get_current_page()
    result_text = await page.evaluate(
        """(payload) => {
            const original = String(payload.query || '').trim();
            const kindHint = String(payload.kind_hint || '').trim().toLowerCase();
            const normalize = (value) =>
              String(value || '')
                .toLowerCase()
                .replace(/[^a-z0-9]+/g, ' ')
                .replace(/\\s+/g, ' ')
                .trim();
            const q = normalize(original);
            const tokens = q
              .split(/\\s+/)
              .filter((token) => token && (token.length > 1 || q.length <= 2));
            const shortQuery = tokens.length === 1 && tokens[0].length <= 2;
            const isVisible = (el) => {
              const rect = el.getBoundingClientRect();
              const style = window.getComputedStyle(el);
              return rect.width > 0
                && rect.height > 0
                && style.visibility !== 'hidden'
                && style.display !== 'none';
            };
            const selector = [
              'button',
              'a[href]',
              '[role="button"]',
              '[role="link"]',
              '[role="tab"]',
              'input[type="button"]',
              'input[type="submit"]',
              'summary'
            ].join(',');

            const seen = new Set();
            const candidates = [];
            for (const el of Array.from(document.querySelectorAll(selector))) {
              if (!isVisible(el)) continue;
              if (seen.has(el)) continue;
              seen.add(el);
              const rawLabel = (
                el.innerText ||
                el.textContent ||
                el.getAttribute('aria-label') ||
                el.getAttribute('title') ||
                el.getAttribute('value') ||
                ''
              ).trim();
              const label = normalize(rawLabel);
              const href = String(el.href || el.getAttribute('href') || '');
              if (!label) continue;

              let score = 0;
              if (label === q) score += 120;
              if (rawLabel.trim().toLowerCase() === original.toLowerCase()) score += 25;
              if (q && !shortQuery && label.includes(q)) score += 40;
              const allTokensPresent = tokens.length > 0 && tokens.every((token) => label.includes(token));
              if (allTokensPresent) score += 20;
              for (const token of tokens) {
                const boundary = new RegExp(`(^|\\\\s)${token.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')}(\\\\s|$)`, 'i');
                if (boundary.test(label)) {
                  score += 12;
                } else if (!shortQuery && label.includes(token)) {
                  score += 4;
                }
              }

              const tag = String(el.tagName || '').toLowerCase();
              const role = String(el.getAttribute('role') || '').toLowerCase();
              if (tag === 'button' || role === 'button') score += 18;
              if (role === 'tab') score += 10;
              if (tag === 'a' || role === 'link') score += 8;
              if ((el.getAttribute('aria-label') || '').trim().toLowerCase() === original.toLowerCase()) score += 18;
              if ((el.getAttribute('title') || '').trim().toLowerCase() === original.toLowerCase()) score += 12;
              const handleMatch = original.toLowerCase().match(/@([a-z0-9_]+)/i);
              if (handleMatch) {
                const handle = handleMatch[1].toLowerCase();
                if (rawLabel.toLowerCase().includes(`@${handle}`)) score += 40;
                if (href.toLowerCase().includes(`/${handle}`)) score += 55;
              }
              if (kindHint === 'button') {
                if (tag === 'button' || role === 'button' || tag === 'input') score += 24;
                if (tag === 'a' || role === 'link') score -= 10;
              } else if (kindHint === 'link') {
                if (tag === 'a' || role === 'link') score += 24;
                if (tag === 'button' || role === 'button') score -= 8;
              } else if (kindHint === 'tab') {
                if (role === 'tab') score += 24;
              }
              const aria = (el.getAttribute('aria-label') || '').trim().toLowerCase();
              const title = (el.getAttribute('title') || '').trim().toLowerCase();
              if (shortQuery && q === 'x') {
                if (label === 'x') score += 80;
                if (aria.includes('close') || title.includes('close') || label === 'close' || label === 'dismiss') {
                  score += 95;
                }
                if (tag === 'button' || role === 'button') score += 22;
                if (tag === 'a' || role === 'link') score -= 20;
              }

              if (score <= 0) continue;
              candidates.push({
                el,
                score,
                rawLabel,
                href,
                tag,
                role,
              });
            }

            candidates.sort((a, b) => b.score - a.score);
            const best = candidates[0];
            if (!best) {
              return JSON.stringify({ok:false,error:`Could not find a clickable target for "${original}".`});
            }

            best.el.click();
            return JSON.stringify({
              ok:true,
              label: best.rawLabel,
              href: best.href,
              score: best.score,
              tag: best.tag,
              role: best.role,
            });
        }""",
        {"query": text, "kind_hint": kind_hint or ""},
    )
    result = json.loads(result_text or "{}")
    if result.get("ok"):
        await asyncio.sleep(0.5)
        new_state = await browser.get_browser_state_summary(include_screenshot=False)
        after_url = str(new_state.url or "")
        after_title = str(new_state.title or "")
        href = str(result.get("href") or "")
        href_no_hash = href.split("#", 1)[0]
        before_no_hash = before_url.split("#", 1)[0]
        after_no_hash = after_url.split("#", 1)[0]
        navigated = (
            after_no_hash != before_no_hash
            or after_title != before_title
            or (href_no_hash and href_no_hash in after_no_hash)
            or (href_no_hash and after_no_hash in href_no_hash)
        )
        if href and not href.startswith("#") and (kind_hint == "link" or result.get("tag") == "a" or result.get("role") == "link"):
            if not navigated:
                raise RuntimeError(f"Clicked '{result.get('label') or text}' but the page did not change.")
        return {
            "label": result.get("label") or text,
            "href": result.get("href"),
            "match_score": result.get("score"),
            "match_tag": result.get("tag"),
            "match_role": result.get("role"),
            "before_url": before_url,
            "url": new_state.url,
            "title": new_state.title,
        }

    state = await browser.get_browser_state_summary(include_screenshot=False)
    state_text = state.dom_state.llm_representation()
    click_index = find_best_index(
        state_text,
        text,
        preferred_tags=("<button", "<a", "role=button"),
        preferred_terms=("aria-label",),
    )
    if click_index is None:
        raise RuntimeError(result.get("error") or f"Could not find a clickable target for '{text}'.")

    node = await browser.get_element_by_index(click_index)
    if node is None:
        raise RuntimeError(f"Clickable target index {click_index} disappeared.")
    element = await page.get_element(node.backend_node_id)
    await element.click()
    await asyncio.sleep(0.5)

    new_state = await browser.get_browser_state_summary(include_screenshot=False)
    return {
        "click_index": click_index,
        "label": text,
        "url": new_state.url,
        "title": new_state.title,
    }


async def _open_route(browser: Browser, route: str) -> dict:
    state = await browser.get_browser_state_summary(include_screenshot=False)
    current_url = str(state.url or "").lower()

    if route == "browser":
        return {"route": route, "url": state.url, "title": state.title}

    if route == "messages":
        if "linkedin.com" in current_url or not current_url:
            target_url = "https://www.linkedin.com/messaging/"
            await _open_url(browser, target_url)
            state = await browser.get_browser_state_summary(include_screenshot=False)
            return {"route": route, "url": state.url, "title": state.title}
        try:
            return await _click_text(browser, "Messages", kind_hint="link")
        except Exception:
            return await _click_text(browser, "Messaging", kind_hint="link")

    if route == "notifications":
        if "linkedin.com" in current_url or not current_url:
            target_url = "https://www.linkedin.com/notifications/"
            await _open_url(browser, target_url)
            state = await browser.get_browser_state_summary(include_screenshot=False)
            return {"route": route, "url": state.url, "title": state.title}
        return await _click_text(browser, "Notifications", kind_hint="link")

    if route == "network":
        target_url = "https://www.linkedin.com/mynetwork/"
        await _open_url(browser, target_url)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title}

    if route == "playback_toggle":
        page = await browser.must_get_current_page()
        if "youtube.com" in current_url:
            await page.press("k")
        else:
            await page.press("Space")
        await asyncio.sleep(0.15)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title}

    page = await browser.must_get_current_page()

    if route == "mute_toggle":
        if "youtube.com" in current_url:
            await page.press("m")
        else:
            raise RuntimeError("Mute toggle is only supported directly on YouTube.")
        await asyncio.sleep(0.15)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title}

    if route == "fullscreen_toggle":
        if "youtube.com" in current_url:
            await page.press("f")
        else:
            await page.press("Meta+Control+f")
        await asyncio.sleep(0.2)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title}

    if route == "seek_forward":
        if "youtube.com" not in current_url:
            raise RuntimeError("Seek forward is only supported directly on YouTube.")
        await page.press("l")
        await asyncio.sleep(0.1)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title}

    if route == "seek_backward":
        if "youtube.com" not in current_url:
            raise RuntimeError("Seek backward is only supported directly on YouTube.")
        await page.press("j")
        await asyncio.sleep(0.1)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title}

    if route == "back":
        await page.go_back()
        await asyncio.sleep(0.35)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title}

    if route == "forward":
        await page.go_forward()
        await asyncio.sleep(0.35)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title}

    if route == "reload":
        await page.reload()
        await asyncio.sleep(0.35)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title}

    if route == "hard_reload":
        await page.press("Meta+Shift+r")
        await asyncio.sleep(0.45)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title}

    if route == "new_tab":
        await page.press("Meta+t")
        await asyncio.sleep(0.15)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title}

    if route == "close_tab":
        await page.press("Meta+w")
        await asyncio.sleep(0.15)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title}

    if route == "reopen_tab":
        await page.press("Meta+Shift+t")
        await asyncio.sleep(0.2)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title}

    if route == "next_tab":
        await page.press("Control+Tab")
        await asyncio.sleep(0.15)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title}

    if route == "previous_tab":
        await page.press("Control+Shift+Tab")
        await asyncio.sleep(0.15)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title}

    if route == "address_bar":
        await page.press("Meta+l")
        await asyncio.sleep(0.1)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title}

    if route == "scroll_top":
        result = await _scroll_container(page, mode="top")
        await asyncio.sleep(0.1)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title, **result}

    if route == "scroll_bottom":
        result = await _scroll_container(page, mode="bottom")
        await asyncio.sleep(0.1)
        state = await browser.get_browser_state_summary(include_screenshot=False)
        return {"route": route, "url": state.url, "title": state.title, **result}

    raise RuntimeError(f"Unsupported route '{route}'")


async def _switch_to_tab(browser: Browser, tab_index: int) -> dict:
    page = await browser.must_get_current_page()
    await page.press(f"Meta+{tab_index}")
    await asyncio.sleep(0.15)
    state = await browser.get_browser_state_summary(include_screenshot=False)
    return {
        "route": "tab_index",
        "tab_index": tab_index,
        "url": state.url,
        "title": state.title,
    }


async def _click_first_candidate(browser: Browser, kind: str, query: Optional[str]) -> dict:
    before_state = await browser.get_browser_state_summary(include_screenshot=False)
    before_url = str(before_state.url or "")
    before_title = str(before_state.title or "")
    page = await browser.must_get_current_page()
    result_text = await page.evaluate(
        """(opts) => {
            const kind = String(opts.kind || 'link');
            const query = String(opts.query || '').trim().toLowerCase();
            const tokens = query.split(/\\s+/).filter(Boolean);
            const selectors = {
              link: 'a[href]',
              result: 'a[href], button, [role="button"]',
              profile: 'a[href*="/in/"]',
              video: 'a#video-title, a[href*="/watch"]',
              tab: 'a[href], button, [role="tab"], [role="button"]'
            };
            const selector = selectors[kind] || selectors.link;
            const isVisible = (el) => {
              const rect = el.getBoundingClientRect();
              const style = window.getComputedStyle(el);
              return rect.width > 0
                && rect.height > 0
                && style.visibility !== 'hidden'
                && style.display !== 'none';
            };
            const score = (el) => {
              const text = (el.innerText || el.textContent || '').trim().toLowerCase();
              if (!tokens.length) return 1;
              let total = 0;
              for (const token of tokens) {
                if (text.includes(token)) total += 1;
              }
              return total;
            };
            const visible = Array.from(document.querySelectorAll(selector)).filter(isVisible);
            if (!visible.length) {
              return JSON.stringify({ok:false,error:`No visible candidate found for ${kind}.`});
            }
            let candidates = visible;
            if (tokens.length) {
              const scored = visible
                .map((el) => ({el, score: score(el)}))
                .filter((entry) => entry.score > 0)
                .sort((a, b) => b.score - a.score);
              if (scored.length) {
                candidates = scored.map((entry) => entry.el);
              }
            }
            const target = candidates[0];
            if (!target) {
              return JSON.stringify({ok:false,error:`No matching candidate found for ${query || kind}.`});
            }
            const label = (target.innerText || target.textContent || target.getAttribute('aria-label') || '').trim();
            const href = target.href || target.getAttribute('href') || '';
            target.click();
            return JSON.stringify({ok:true,label,href});
        }""",
        {"kind": kind, "query": query or ""},
    )
    result = json.loads(result_text or "{}")
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or f"Could not click first {kind}.")
    await asyncio.sleep(0.5)
    state = await browser.get_browser_state_summary(include_screenshot=False)
    href = str(result.get("href") or "")
    href_no_hash = href.split("#", 1)[0]
    before_no_hash = before_url.split("#", 1)[0]
    after_no_hash = str(state.url or "").split("#", 1)[0]
    navigated = (
        after_no_hash != before_no_hash
        or str(state.title or "") != before_title
        or (href_no_hash and href_no_hash in after_no_hash)
        or (href_no_hash and after_no_hash in href_no_hash)
    )
    if kind in {"link", "profile", "video"} and href and not href.startswith("#") and not navigated:
        raise RuntimeError(f"Clicked first matching {kind} but the page did not change.")
    return {
        "kind": kind,
        "query": query,
        "label": result.get("label") or f"First {kind}",
        "href": result.get("href"),
        "before_url": before_url,
        "url": state.url,
        "title": state.title,
    }


async def _scroll_page(browser: Browser, direction: str, amount: int) -> dict:
    page = await browser.must_get_current_page()
    result = await _scroll_container(page, direction=direction, amount=amount, mode="relative")
    if not result.get("changed"):
        before = await _scroll_container(page, mode="inspect")
        key = "PageUp" if direction == "up" else "PageDown"
        await page.press(key)
        await asyncio.sleep(0.15)
        after = await _scroll_container(page, mode="inspect")
        after["changed"] = abs((after.get("after") or 0) - (before.get("after") or 0)) >= 4
        result = after
    await asyncio.sleep(0.15)
    state = await browser.get_browser_state_summary(include_screenshot=False)
    return {
        "direction": direction,
        "amount": amount,
        **result,
        "url": state.url,
        "title": state.title,
    }


async def run_command(command: str, profile_directory: str) -> dict:
    intent = parse_intent(command)
    if not any(
        [
            intent.url,
            intent.open_in_new_tab,
            intent.search_query,
            intent.scroll_text,
            intent.scroll_direction,
            intent.click_text,
            intent.open_first_video,
            intent.route,
            intent.click_first_kind,
            intent.profile_query,
            intent.video_query,
            intent.tab_index,
        ]
    ):
        return {"success": False, "error": "Unsupported browser command for direct browser-use helper."}

    browser = build_browser(profile_directory)
    try:
        await browser.start()
        return await run_command_in_browser(command, browser)
    finally:
        await browser.stop()


def build_browser(profile_directory: str) -> Browser:
    cdp_url = os.getenv("BROWSER_USE_CDP_URL", "").strip()
    if cdp_url:
        return Browser(
            cdp_url=cdp_url,
            headless=False,
            keep_alive=True,
            minimum_wait_page_load_time=0.2,
            wait_for_network_idle_page_load_time=0.5,
            wait_between_actions=0.05,
        )

    return Browser.from_system_chrome(
        profile_directory=profile_directory,
        headless=False,
        keep_alive=True,
        minimum_wait_page_load_time=0.2,
        wait_for_network_idle_page_load_time=0.5,
        wait_between_actions=0.05,
    )


def _same_site(actual_url: str, target_url: str) -> bool:
    actual = urlparse(actual_url or "")
    target = urlparse(target_url or "")
    if not actual.netloc or not target.netloc:
        return False
    actual_host = actual.netloc.lower().removeprefix("www.")
    target_host = target.netloc.lower().removeprefix("www.")
    aliases = {
        ("twitter.com", "x.com"),
        ("x.com", "twitter.com"),
    }
    return actual_host == target_host or (actual_host, target_host) in aliases


def _build_agent_task(text: str, required_url: Optional[str] = None) -> str:
    template = _DEFAULT_SYSTEM_PROMPT
    if _SYSTEM_PROMPT_PATH.exists():
        template = _SYSTEM_PROMPT_PATH.read_text()
    prompt = text
    if required_url:
        prompt += (
            f"\n\nCritical success condition: the active browser tab must end on {required_url} "
            "or the corresponding site before you finish."
        )
    return template.replace("[user prompt]", prompt)


async def _run_agent_once(
    command: str,
    browser: Browser,
    model_name: str,
    required_url: Optional[str],
) -> tuple[str, dict]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required for browser-use agent fallback.")

    llm = ChatAnthropic(
        model=model_name,
        api_key=api_key,
    )
    agent = Agent(
        task=_build_agent_task(command, required_url=required_url),
        llm=llm,
        browser_session=browser,
        use_thinking=False,
        flash_mode=_is_enabled("BROWSER_USE_FLASH", default=True),
        use_judge=False,
        enable_planning=False,
        max_actions_per_step=2,
        max_failures=3,
        step_timeout=int(os.getenv("BROWSER_USE_AGENT_STEP_TIMEOUT", "90")),
    )
    started_at = time.perf_counter()
    result = await agent.run()
    state = await browser.get_browser_state_summary(include_screenshot=False)
    payload = {
        "url": state.url,
        "title": state.title,
        "summary": result.final_result() or f"Completed browser action for '{command}' on {state.title or state.url}.",
        "timings": {
            "agent_fallback_ms": round((time.perf_counter() - started_at) * 1000.0, 1),
        },
    }
    return result.final_result() or "", payload


def _agent_navigation_satisfied(before_url: str, after_url: str, required_url: Optional[str]) -> bool:
    if not required_url:
        return True
    if not after_url:
        return False
    if _same_site(after_url, required_url):
        return True
    return before_url != after_url and _same_site(after_url, required_url)


async def run_agent_fallback_in_browser(command: str, browser: Browser) -> dict:
    normalized_command = normalize_browser_command(command)
    before_state = await browser.get_browser_state_summary(include_screenshot=False)
    before_url = str(before_state.url or "")
    required_url = parse_intent(normalized_command).url

    model_name = os.getenv("BROWSER_USE_MODEL", "claude-3-5-haiku-20241022")
    _, payload = await _run_agent_once(normalized_command, browser, model_name, required_url)
    after_url = str(payload.get("url") or "")

    if _agent_navigation_satisfied(before_url, after_url, required_url):
        return {
            "success": True,
            "mode": "agent",
            "command": normalized_command,
            "model": model_name,
            **payload,
        }

    retry_model = os.getenv("BROWSER_USE_RETRY_MODEL", "claude-sonnet-4-20250514")
    if retry_model == model_name:
        return {
            "success": False,
            "command": normalized_command,
            "error": f"Agent fallback did not reach {required_url or 'the requested destination'}",
            "model": model_name,
            **payload,
        }

    _, retry_payload = await _run_agent_once(normalized_command, browser, retry_model, required_url)
    retry_after_url = str(retry_payload.get("url") or "")
    if not _agent_navigation_satisfied(before_url, retry_after_url, required_url):
        return {
            "success": False,
            "command": normalized_command,
            "error": f"Agent fallback did not reach {required_url or 'the requested destination'}",
            "model": retry_model,
            **retry_payload,
        }

    retry_payload.setdefault("timings", {})
    first_ms = (payload.get("timings") or {}).get("agent_fallback_ms", 0.0)
    second_ms = (retry_payload.get("timings") or {}).get("agent_fallback_ms", 0.0)
    retry_payload["timings"]["agent_fallback_ms_total"] = round(first_ms + second_ms, 1)
    retry_payload["retried_from_model"] = model_name
    return {
        "success": True,
        "mode": "agent",
        "command": normalized_command,
        "model": retry_model,
        **retry_payload,
    }


async def run_command_in_browser(command: str, browser: Browser) -> dict:
    normalized_command = normalize_browser_command(command)
    started_at = time.perf_counter()
    intent = parse_intent(normalized_command)
    if not any(
        [
            intent.url,
            intent.open_in_new_tab,
            intent.search_query,
            intent.scroll_text,
            intent.scroll_direction,
            intent.click_text,
            intent.open_first_video,
            intent.route,
            intent.click_first_kind,
            intent.profile_query,
            intent.video_query,
            intent.tab_index,
        ]
    ):
        return {"success": False, "error": "Unsupported browser command for direct browser-use helper."}

    try:
        result: dict = {
            "success": True,
            "mode": "direct",
            "command": normalized_command,
            "actions": [],
        }

        if intent.open_in_new_tab:
            route_result = await _open_route(browser, "new_tab")
            result["actions"].append({"tool": "route", "route": "new_tab", **route_result})

        if intent.url:
            await _open_url(browser, intent.url)
            result["actions"].append({"tool": "open", "url": intent.url})

        if intent.search_query:
            search_result = await _fill_search(browser, intent.search_query)
            result["actions"].append({"tool": "search", "query": intent.search_query, **search_result})

        if intent.open_first_video:
            open_result = await _open_first_youtube_video(browser)
            result["actions"].append({"tool": "open_first_video", **open_result})

        if intent.route:
            route_result = await _open_route(browser, intent.route)
            result["actions"].append({"tool": "route", "route": intent.route, **route_result})

        if intent.tab_index is not None:
            tab_result = await _switch_to_tab(browser, intent.tab_index)
            result["actions"].append({"tool": "switch_tab", **tab_result})

        if intent.click_first_kind:
            first_result = await _click_first_candidate(
                browser,
                intent.click_first_kind,
                intent.click_first_query,
            )
            result["actions"].append(
                {
                    "tool": "click_first",
                    "kind": intent.click_first_kind,
                    "query": intent.click_first_query,
                    **first_result,
                }
            )

        if intent.profile_query:
            profile_result = await _click_first_candidate(browser, "profile", intent.profile_query)
            result["actions"].append(
                {
                    "tool": "click_profile",
                    "query": intent.profile_query,
                    **profile_result,
                }
            )

        if intent.video_query:
            video_result = await _click_video_candidate(browser, intent.video_query)
            result["actions"].append(
                {
                    "tool": "click_video",
                    "query": intent.video_query,
                    **video_result,
                }
            )

        if intent.scroll_direction:
            scroll_page_result = await _scroll_page(
                browser,
                intent.scroll_direction,
                intent.scroll_amount,
            )
            result["actions"].append({"tool": "scroll_page", **scroll_page_result})

        if intent.scroll_text:
            scroll_result = await _scroll_to_text(browser, intent.scroll_text)
            result["actions"].append({"tool": "scroll_to_text", **scroll_result})

        if intent.click_text:
            click_result = await _click_text(browser, intent.click_text, intent.click_kind_hint)
            result["actions"].append({"tool": "click_text", **click_result})

        state = await browser.get_browser_state_summary(include_screenshot=False)
        result["url"] = state.url
        result["title"] = state.title
        result["summary"] = f"Completed browser action for '{normalized_command}' on {state.title or state.url}."
        result["timings"] = {
            "direct_helper_ms": round((time.perf_counter() - started_at) * 1000.0, 1),
        }
        return result
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "command": normalized_command,
            "timings": {
                "direct_helper_ms": round((time.perf_counter() - started_at) * 1000.0, 1),
            },
        }


async def run_best_effort_command_in_browser(command: str, browser: Browser) -> dict:
    direct_result = await run_command_in_browser(command, browser)
    if direct_result.get("success"):
        return direct_result

    agent_result = await run_agent_fallback_in_browser(command, browser)
    if agent_result.get("success"):
        agent_result["fallback_from"] = direct_result.get("error")
        direct_ms = (direct_result.get("timings") or {}).get("direct_helper_ms")
        if direct_ms is not None:
            agent_result.setdefault("timings", {})["direct_helper_ms_before_fallback"] = direct_ms
        return agent_result

    direct_error = str(direct_result.get("error") or "").strip()
    agent_error = str(agent_result.get("error") or "").strip()
    if direct_error and agent_error:
        return {
            "success": False,
            "command": command,
            "error": f"Direct browser path failed: {direct_error}. Agent fallback failed: {agent_error}",
        }
    return direct_result if direct_error else agent_result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", help="Natural-language browser command")
    parser.add_argument(
        "--profile-directory",
        default=os.getenv("BROWSER_USE_PROFILE", "Default"),
        help="Chrome profile directory name, e.g. Default or 'Profile 1'",
    )
    args = parser.parse_args()

    try:
        payload = asyncio.run(run_command(args.command, args.profile_directory))
    except Exception as exc:
        payload = {"success": False, "error": str(exc), "command": args.command}
    print(json.dumps(payload))
    return 0 if payload.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
