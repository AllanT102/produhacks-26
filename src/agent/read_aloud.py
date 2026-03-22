"""Direct read-aloud command handling for browser pages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from src.shared.speech_output import speak_text
from src.tool_runtime.tools.browser import browser_extract_text

StatusCallback = Callable[[str, str], Awaitable[None]]

_POLITE_PREFIXES = (
    "please ",
    "can you ",
    "could you ",
    "would you ",
    "will you ",
    "can u ",
)


@dataclass(frozen=True)
class ReadAloudRequest:
    """Parsed readback request from a transcript."""

    scope: str
    max_blocks: int
    max_chars: int
    fallback_scope: str = ""


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _strip_polite_prefixes(text: str) -> str:
    stripped = text
    while True:
        lowered = stripped.lower()
        for prefix in _POLITE_PREFIXES:
            if lowered.startswith(prefix):
                stripped = stripped[len(prefix):].strip()
                break
        else:
            return stripped


def parse_read_aloud_request(text: str) -> Optional[ReadAloudRequest]:
    """Recognize explicit browser readback commands."""
    stripped = _strip_polite_prefixes(_normalize(text)).strip(" .!?")
    lowered = stripped.lower()
    if not lowered.startswith("read "):
        return None

    subject = lowered[5:].strip()
    subject = re.sub(r"\b(?:out loud|aloud|to me|for me|back to me|please)\b", "", subject)
    subject = _normalize(subject).strip(" .")
    if not subject:
        return ReadAloudRequest(scope="page", fallback_scope="headline", max_blocks=5, max_chars=1100)

    if subject in {
        "selection",
        "the selection",
        "selected text",
        "the selected text",
        "highlighted text",
        "the highlighted text",
    }:
        return ReadAloudRequest(scope="selection", max_blocks=1, max_chars=850)

    if subject in {
        "headline",
        "the headline",
        "heading",
        "the heading",
        "title",
        "the title",
    }:
        return ReadAloudRequest(scope="headline", max_blocks=1, max_chars=260)

    if subject in {
        "first paragraph",
        "the first paragraph",
        "opening paragraph",
        "the opening paragraph",
        "intro paragraph",
        "the intro paragraph",
        "lead paragraph",
        "the lead paragraph",
    }:
        return ReadAloudRequest(
            scope="first_paragraph",
            fallback_scope="page",
            max_blocks=2,
            max_chars=700,
        )

    if subject in {
        "feed",
        "the feed",
        "post",
        "the post",
        "this post",
        "that post",
        "story",
        "the story",
        "this story",
        "that story",
        "article",
        "the article",
        "this article",
        "that article",
        "card",
        "the card",
        "this card",
        "that card",
    }:
        return ReadAloudRequest(
            scope="focus",
            fallback_scope="page",
            max_blocks=5,
            max_chars=900,
        )

    if subject in {
        "this",
        "that",
        "this part",
        "that part",
        "this text",
        "that text",
    }:
        return ReadAloudRequest(
            scope="selection",
            fallback_scope="page",
            max_blocks=4,
            max_chars=900,
        )

    page_subjects = {
        "page",
        "the page",
        "this page",
        "that page",
        "article",
        "the article",
        "this article",
        "that article",
        "website",
        "the website",
        "site",
        "the site",
    }
    if subject in page_subjects:
        return ReadAloudRequest(scope="page", fallback_scope="headline", max_blocks=5, max_chars=1100)

    return ReadAloudRequest(scope="focus", fallback_scope="page", max_blocks=5, max_chars=900)


def _scope_label(scope: str) -> str:
    return {
        "selection": "selected text",
        "headline": "headline",
        "first_paragraph": "first paragraph",
        "focus": "current story",
        "page": "page",
    }.get(scope, "page")


async def maybe_execute_read_aloud(
    text: str,
    on_status: Optional[StatusCallback] = None,
) -> Optional[str]:
    """Handle supported read-aloud commands before the slower browser planner path."""
    request = parse_read_aloud_request(text)
    if request is None:
        return None

    extraction = browser_extract_text(
        scope=request.scope,
        fallback_scope=request.fallback_scope,
        max_blocks=request.max_blocks,
        max_chars=request.max_chars,
    )
    if not extraction.get("ok"):
        message = extraction.get("error") or "Could not extract text from the active Chrome page."
        raise RuntimeError(str(message))

    spoken_text = str(extraction.get("text") or "").strip()
    if not spoken_text:
        raise RuntimeError("Could not find readable text on the active Chrome page.")

    scope_used = str(extraction.get("scope") or request.scope)
    if on_status is not None:
        await on_status("speaking", "Reading {}".format(_scope_label(scope_used)))

    speech = await speak_text(spoken_text)
    page_title = str(extraction.get("title") or extraction.get("url") or "page").strip()
    truncated = bool(extraction.get("truncated"))
    summary = "Read the {} from {} aloud".format(_scope_label(scope_used), page_title)
    if truncated:
        summary += " (trimmed to the beginning)"
    summary += "."
    if request.scope == "selection" and scope_used != "selection":
        summary = "No selection found, so I read the {} from {} aloud.".format(_scope_label(scope_used), page_title)
    if speech.voice != "default":
        summary += f" Voice: {speech.voice}."
    return summary
