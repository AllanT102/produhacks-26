"""Shared event types."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class TranscriptEvent:
    type: Literal["partial", "final"]
    transcript_id: str
    text: str
    timestamp: float


@dataclass
class ToolCall:
    tool: str
    args: dict


@dataclass
class ToolResult:
    ok: bool
    tool: str
    result: dict | None = None
    error: dict | None = None
