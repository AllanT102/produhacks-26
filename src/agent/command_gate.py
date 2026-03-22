"""Heuristics for deciding whether a finalized transcript looks executable."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandGateDecision:
    """Result of checking whether a transcript looks like an actual command."""

    should_execute: bool
    reason: str


_POLITE_PREFIXES = (
    "please ",
    "can you ",
    "could you ",
    "would you ",
    "will you ",
    "can u ",
)

_ACTION_PREFIXES = (
    "back ",
    "go back",
    "forward ",
    "go forward",
    "reload ",
    "refresh ",
    "close ",
    "new tab",
    "open new tab",
    "reopen ",
    "undo close ",
    "next tab",
    "previous tab",
    "prev tab",
    "switch to ",
    "focus ",
    "press ",
    "open ",
    "go to ",
    "search ",
    "search for ",
    "search up ",
    "find ",
    "look up ",
    "check ",
    "show ",
    "show me ",
    "click ",
    "click on ",
    "scroll ",
    "play ",
    "pause",
    "resume",
    "stop",
    "mute",
    "unmute",
    "fullscreen",
    "enter fullscreen",
    "exit fullscreen",
    "go fullscreen",
    "message ",
    "reply ",
    "send ",
    "type ",
    "write ",
    "read ",
    "open my ",
    "check my ",
)

_ACTION_KEYWORDS = (
    "linkedin",
    "youtube",
    "gmail",
    "google",
    "messages",
    "message",
    "notifications",
    "profile",
    "tab",
    "link",
    "video",
    "result",
    "browser",
    "chrome",
    "safari",
    "connect",
    "follow",
    "reload",
    "refresh",
    "tab",
    "back",
    "forward",
    "fullscreen",
)

_NON_COMMAND_PREFIXES = (
    "i ",
    "i'm ",
    "im ",
    "i love ",
    "we ",
    "we're ",
    "were ",
    "yeah ",
    "yep ",
    "nope ",
    "okay ",
    "ok ",
    "well ",
    "that ",
    "this ",
    "what the ",
    "why ",
    "how ",
    "when ",
    "isaac, ",
)


def _contains_phrase(text: str, phrase: str) -> bool:
    escaped = re.escape(phrase.strip())
    escaped = escaped.replace(r"\ ", r"\s+")
    return re.search(rf"\b{escaped}\b", text) is not None


def _contains_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(_contains_phrase(text, phrase) for phrase in phrases)


def _token_count(text: str) -> int:
    return len([token for token in re.split(r"\s+", text.strip()) if token])


def should_execute_final_transcript(text: str, source: str) -> CommandGateDecision:
    """Return whether a transcript should be forwarded to the agent."""
    normalized = " ".join(text.strip().split())
    lower = normalized.lower().strip(" .!?")
    if not lower:
        return CommandGateDecision(False, "empty")

    if source in {"typed", "wispr", "fake_transcript"}:
        return CommandGateDecision(True, "interactive-source")

    if lower in {"okay", "ok", "thanks", "thank you", "(laughing)", "lol", "haha"}:
        return CommandGateDecision(False, "filler")

    if re.fullmatch(r"[\W_]+", lower):
        return CommandGateDecision(False, "non-word")

    stripped = lower
    for prefix in _POLITE_PREFIXES:
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix):].strip()
            break

    while stripped.startswith("just "):
        stripped = stripped[5:].strip()

    if any(stripped.startswith(prefix) for prefix in _ACTION_PREFIXES):
        message_match = re.search(r"\b(?:send|write|reply)\b.*\b(?:say|saying)\b\s+(.+)$", stripped)
        if message_match:
            body = message_match.group(1).strip()
            if len(body.split()) < 2:
                return CommandGateDecision(False, "incomplete-dictation")
        return CommandGateDecision(True, "action-prefix")

    if stripped in {
        "pause",
        "play",
        "stop",
        "mute",
        "unmute",
        "back",
        "forward",
        "reload",
        "refresh",
        "fullscreen",
        "new tab",
        "next tab",
        "previous tab",
    }:
        return CommandGateDecision(True, "single-action")

    if _contains_any_phrase(stripped, _ACTION_KEYWORDS) and _contains_any_phrase(
        stripped,
        ("open", "click", "search", "find", "check", "show", "go", "message"),
    ):
        if _token_count(stripped) > 8:
            return CommandGateDecision(False, "long-ambient-command")
        return CommandGateDecision(True, "action-keyword")

    if any(stripped.startswith(prefix) for prefix in _NON_COMMAND_PREFIXES):
        return CommandGateDecision(False, "conversational-prefix")

    if re.search(r"\b(i|i'm|im|we|we're|were|you know|like)\b", stripped) and not re.search(
        r"\b(open|click|search|find|check|show|go|play|pause|message|reply|send|type|write|read|scroll)\b",
        stripped,
    ):
        return CommandGateDecision(False, "conversational-content")

    if len(stripped.split()) <= 2 and not any(keyword in stripped for keyword in _ACTION_KEYWORDS):
        return CommandGateDecision(False, "too-short")

    return CommandGateDecision(False, "unknown-shape")
