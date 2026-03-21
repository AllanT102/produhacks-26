"""Shared event types."""

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional


@dataclass
class TranscriptEvent:
    type: Literal["partial", "final"]
    transcript_id: str
    text: str
    timestamp: float
    source: str = "microphone"


@dataclass
class ToolCall:
    tool: str
    args: Dict[str, Any]


@dataclass
class ToolResult:
    ok: bool
    tool: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


@dataclass
class AgentCommand:
    transcript_id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
