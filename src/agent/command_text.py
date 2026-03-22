"""Utilities for preparing transcript text for execution."""

import re

_ACTION_VERBS = (
    "open",
    "go",
    "search",
    "find",
    "look",
    "click",
    "scroll",
    "read",
    "check",
    "show",
    "press",
    "close",
    "play",
    "pause",
    "message",
    "reply",
    "send",
    "say",
    "type",
    "write",
    "fill",
)


def _contains_action_phrase(text: str) -> bool:
    lowered = text.lower().strip()
    if not lowered:
        return False
    return re.search(r"\b(?:%s)\b" % "|".join(_ACTION_VERBS), lowered) is not None


def _trim_to_action_phrase(text: str) -> str:
    match = re.search(r"\b(?:%s)\b" % "|".join(_ACTION_VERBS), text, flags=re.IGNORECASE)
    if not match:
        return text
    return text[match.start():].strip(" \t\r\n.,!?;:()[]{}\"'`-–—•*")


def canonicalize_command_text(text: str) -> str:
    """Normalize whitespace and collapse obvious repeated sentence duplicates."""
    normalized = " ".join(text.strip().split())
    if not normalized:
        return normalized

    parts = []
    for raw_part in re.split(r"[.!?]+", normalized):
        part = raw_part.strip(" \t\r\n.,!?;:()[]{}\"'`-–—•*")
        if not part:
            continue
        if not re.search(r"[A-Za-z0-9@]", part):
            continue
        parts.append(part)
    if not parts:
        return normalized

    lowered = [part.lower() for part in parts]
    if len(lowered) > 1 and len(set(lowered)) == 1:
        return parts[0]

    deduped_parts = []
    seen_run = None
    for part in parts:
        lower = part.lower()
        if lower == seen_run:
            continue
        deduped_parts.append(part)
        seen_run = lower

    action_parts = [_trim_to_action_phrase(part) for part in deduped_parts if _contains_action_phrase(part)]
    if action_parts:
        return ". ".join(action_parts)

    if deduped_parts:
        return ". ".join(deduped_parts)
    return normalized
