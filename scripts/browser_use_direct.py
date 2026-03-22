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
    search_query: Optional[str] = None
    scroll_text: Optional[str] = None
    click_text: Optional[str] = None
    open_first_video: bool = False


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clean_search_query(value: str) -> str:
    query = _normalize_whitespace(value).strip(" .")
    query = re.sub(
        r"\s+(?:on\s+(?:youtube|linkedin|google)|and\s+(?:play|open|click|subscribe|pause|scroll).*)$",
        "",
        query,
        flags=re.IGNORECASE,
    )
    return query.strip(" .")


def _is_enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _direct_search_url(lower: str, search_query: Optional[str]) -> Optional[str]:
    if not search_query:
        return None
    if "youtube" in lower:
        return f"https://www.youtube.com/results?search_query={quote_plus(search_query)}"
    if "linkedin" in lower:
        return f"https://www.linkedin.com/search/results/all/?keywords={quote_plus(search_query)}&origin=GLOBAL_SEARCH_HEADER"
    return None


def parse_intent(command: str) -> CommandIntent:
    text = _normalize_whitespace(command)
    lower = text.lower()

    search_query = None
    search_patterns = [
        r"\bsearch up (?P<q>.+?)(?:,| then | and (?:open|click|subscribe|pause|scroll|play)\b|$)",
        r"\bsearch for (?P<q>.+?)(?:,| then | and (?:open|click|subscribe|pause|scroll)\b|$)",
        r"\bsearch (?P<q>.+?)(?:,| then | and (?:open|click|subscribe|pause|scroll)\b|$)",
    ]
    for pattern in search_patterns:
        match = re.search(pattern, lower, flags=re.IGNORECASE)
        if match:
            search_query = _clean_search_query(text[match.start("q"):match.end("q")])
            break

    url_match = re.search(r"https?://\S+", text)
    if url_match:
        url = url_match.group(0).rstrip(".,)")
    else:
        url = _direct_search_url(lower, search_query)
        if url is not None:
            search_query = None
        elif "youtube" in lower:
            url = "https://www.youtube.com"
        elif "linkedin" in lower:
            url = "https://www.linkedin.com/feed/"
        else:
            url = None

    scroll_text = None
    scroll_match = re.search(r"\bscroll to (?P<t>.+?)(?:,| then | and |$)", lower, flags=re.IGNORECASE)
    if scroll_match:
        scroll_text = _normalize_whitespace(text[scroll_match.start("t"):scroll_match.end("t")]).strip(" .")

    click_text = None
    if "subscribe" in lower:
        click_text = "Subscribe"

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

    return CommandIntent(
        url=url,
        search_query=search_query,
        scroll_text=scroll_text,
        click_text=click_text,
        open_first_video=open_first_video,
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


async def _click_text(browser: Browser, text: str) -> dict:
    state = await browser.get_browser_state_summary(include_screenshot=False)
    state_text = state.dom_state.llm_representation()
    click_index = find_best_index(
        state_text,
        text,
        preferred_tags=("<button", "<a", "role=button"),
        preferred_terms=("aria-label",),
    )
    if click_index is None:
        raise RuntimeError(f"Could not find a clickable target for '{text}'.")

    node = await browser.get_element_by_index(click_index)
    if node is None:
        raise RuntimeError(f"Clickable target index {click_index} disappeared.")
    page = await browser.must_get_current_page()
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


async def run_command(command: str, profile_directory: str) -> dict:
    intent = parse_intent(command)
    if not any([intent.url, intent.search_query, intent.scroll_text, intent.click_text]):
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


def _build_agent_task(text: str) -> str:
    template = _DEFAULT_SYSTEM_PROMPT
    if _SYSTEM_PROMPT_PATH.exists():
        template = _SYSTEM_PROMPT_PATH.read_text()
    return template.replace("[user prompt]", text)


async def run_agent_fallback_in_browser(command: str, browser: Browser) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "success": False,
            "error": "ANTHROPIC_API_KEY is required for browser-use agent fallback.",
            "command": command,
        }

    llm = ChatAnthropic(
        model=os.getenv("BROWSER_USE_MODEL", "claude-sonnet-4-20250514"),
        api_key=api_key,
    )
    agent = Agent(
        task=_build_agent_task(command),
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
    result = await agent.run()
    state = await browser.get_browser_state_summary(include_screenshot=False)
    return {
        "success": True,
        "mode": "agent",
        "command": command,
        "url": state.url,
        "title": state.title,
        "summary": result.final_result() or f"Completed browser action for '{command}' on {state.title or state.url}.",
    }


async def run_command_in_browser(command: str, browser: Browser) -> dict:
    intent = parse_intent(command)
    if not any([intent.url, intent.search_query, intent.scroll_text, intent.click_text, intent.open_first_video]):
        return {"success": False, "error": "Unsupported browser command for direct browser-use helper."}

    try:
        result: dict = {
            "success": True,
            "command": command,
            "actions": [],
        }

        if intent.url:
            await _open_url(browser, intent.url)
            result["actions"].append({"tool": "open", "url": intent.url})

        if intent.search_query:
            search_result = await _fill_search(browser, intent.search_query)
            result["actions"].append({"tool": "search", "query": intent.search_query, **search_result})

        if intent.open_first_video:
            open_result = await _open_first_youtube_video(browser)
            result["actions"].append({"tool": "open_first_video", **open_result})

        if intent.scroll_text:
            scroll_result = await _scroll_to_text(browser, intent.scroll_text)
            result["actions"].append({"tool": "scroll_to_text", **scroll_result})

        if intent.click_text:
            click_result = await _click_text(browser, intent.click_text)
            result["actions"].append({"tool": "click_text", **click_result})

        state = await browser.get_browser_state_summary(include_screenshot=False)
        result["url"] = state.url
        result["title"] = state.title
        result["summary"] = f"Completed browser action for '{command}' on {state.title or state.url}."
        return result
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "command": command,
        }


async def run_best_effort_command_in_browser(command: str, browser: Browser) -> dict:
    direct_result = await run_command_in_browser(command, browser)
    if direct_result.get("success"):
        direct_result["mode"] = "direct"
        return direct_result

    agent_result = await run_agent_fallback_in_browser(command, browser)
    if agent_result.get("success"):
        agent_result["fallback_from"] = direct_result.get("error")
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
