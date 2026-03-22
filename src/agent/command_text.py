"""Utilities for preparing transcript text for execution."""

import re


def canonicalize_command_text(text: str) -> str:
    """Normalize whitespace and collapse obvious repeated sentence duplicates."""
    normalized = " ".join(text.strip().split())
    if not normalized:
        return normalized

    parts = []
    for raw_part in re.split(r"[.!?]+", normalized):
        part = raw_part.strip(" \t\r\n.,!?;:()[]{}\"'")
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

    if deduped_parts:
        return ". ".join(deduped_parts)
    return normalized
