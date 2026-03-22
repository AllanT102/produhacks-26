"""Generic direct-command router for low-latency voice control."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from src.shared.events import AgentCommand, ToolCall


@dataclass(frozen=True)
class DirectRoute:
    """A direct action path that can skip the planner."""

    summary: str
    tool_calls: list[ToolCall]


def route_direct_command(command: AgentCommand) -> Optional[DirectRoute]:
    """Return a direct execution plan for simple generic commands."""
    text = " ".join(command.text.strip().lower().split())
    if not text:
        return None

    route = _route_scroll(text)
    if route:
        return route

    route = _route_open(text)
    if route:
        return route

    route = _route_media(text)
    if route:
        return route

    route = _route_volume(text)
    if route:
        return route

    route = _route_brightness(text)
    if route:
        return route

    return None


def _route_scroll(text: str) -> Optional[DirectRoute]:
    if not text.startswith("scroll"):
        return None

    direction = "down"
    if "up" in text:
        direction = "up"
    elif "down" in text:
        direction = "down"

    amount = 6
    if any(token in text for token in ("a bit", "little", "slightly")):
        amount = 3
    if any(token in text for token in ("fast", "faster", "more", "way", "lot")):
        amount = 12

    return DirectRoute(
        summary="Scrolled {}.".format(direction),
        tool_calls=[
            ToolCall(
                tool="scroll",
                args={"x": 720, "y": 450, "direction": direction, "amount": amount},
            )
        ],
    )


def _route_open(text: str) -> Optional[DirectRoute]:
    url_match = re.match(r"^(open|go to)\s+(.+)$", text)
    if not url_match:
        return None

    target = url_match.group(2).strip()
    known_urls = {
        "youtube": "https://www.youtube.com",
        "youtube.com": "https://www.youtube.com",
        "gmail": "https://mail.google.com",
        "google": "https://www.google.com",
        "linkedin": "https://www.linkedin.com",
        "github": "https://github.com",
    }
    if target in known_urls:
        return DirectRoute(
            summary="Opened {}.".format(target),
            tool_calls=[ToolCall(tool="open_app", args={"app": "Google Chrome", "url": known_urls[target]})],
        )

    if "." in target and " " not in target:
        url = target if target.startswith(("http://", "https://")) else "https://{}".format(target)
        return DirectRoute(
            summary="Opened {}.".format(target),
            tool_calls=[ToolCall(tool="open_app", args={"app": "Google Chrome", "url": url})],
        )

    app_aliases = {
        "chrome": "chrome",
        "google chrome": "google chrome",
        "safari": "safari",
        "finder": "finder",
        "terminal": "terminal",
        "slack": "slack",
        "spotify": "spotify",
        "discord": "discord",
        "notes": "notes",
        "calendar": "calendar",
        "mail": "mail",
    }
    if target in app_aliases:
        return DirectRoute(
            summary="Opened {}.".format(target),
            tool_calls=[ToolCall(tool="open_app", args={"app": app_aliases[target]})],
        )

    return None


def _route_media(text: str) -> Optional[DirectRoute]:
    if text in {"pause", "play", "play pause", "pause video", "play video"}:
        return DirectRoute(
            summary="Toggled playback.",
            tool_calls=[ToolCall(tool="key_press", args={"key": "space"})],
        )
    if text in {"fullscreen", "go fullscreen", "enter fullscreen"}:
        return DirectRoute(
            summary="Toggled fullscreen.",
            tool_calls=[ToolCall(tool="key_press", args={"key": "f"})],
        )
    if text in {"exit fullscreen"}:
        return DirectRoute(
            summary="Exited fullscreen.",
            tool_calls=[ToolCall(tool="key_press", args={"key": "esc"})],
        )
    return None


def _route_volume(text: str) -> Optional[DirectRoute]:
    if text in {"mute", "mute volume"}:
        return DirectRoute(
            summary="Muted volume.",
            tool_calls=[ToolCall(tool="set_volume", args={"action": "mute"})],
        )
    if text in {"unmute", "unmute volume"}:
        return DirectRoute(
            summary="Unmuted volume.",
            tool_calls=[ToolCall(tool="set_volume", args={"action": "unmute"})],
        )
    if "volume up" in text or text == "louder":
        steps = 2 if any(token in text for token in ("more", "way", "much")) else 1
        return DirectRoute(
            summary="Raised volume.",
            tool_calls=[ToolCall(tool="set_volume", args={"action": "up", "steps": steps})],
        )
    if "volume down" in text or text == "quieter":
        steps = 2 if any(token in text for token in ("more", "way", "much")) else 1
        return DirectRoute(
            summary="Lowered volume.",
            tool_calls=[ToolCall(tool="set_volume", args={"action": "down", "steps": steps})],
        )
    return None


def _route_brightness(text: str) -> Optional[DirectRoute]:
    if "brightness up" in text or text == "brighter":
        steps = 2 if any(token in text for token in ("more", "way", "much")) else 1
        return DirectRoute(
            summary="Raised brightness.",
            tool_calls=[ToolCall(tool="set_brightness", args={"action": "up", "steps": steps})],
        )
    if "brightness down" in text or text == "dimmer":
        steps = 2 if any(token in text for token in ("more", "way", "much")) else 1
        return DirectRoute(
            summary="Lowered brightness.",
            tool_calls=[ToolCall(tool="set_brightness", args={"action": "down", "steps": steps})],
        )
    return None
