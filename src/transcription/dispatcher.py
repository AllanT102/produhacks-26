"""Dispatch finalized transcripts to the agent."""

import asyncio
import time
from typing import Optional

from src.agent.command_gate import should_execute_final_transcript
from src.agent.command_text import canonicalize_command_text
from src.shared.events import AgentCommand, TranscriptEvent
from src.shared.speech_output import should_suppress_transcripts

_RECENT_FINAL = {"text": "", "at": 0.0}


def _drop_pending_commands(agent_queue: "asyncio.Queue[AgentCommand]") -> int:
    dropped = 0
    while True:
        try:
            agent_queue.get_nowait()
        except asyncio.QueueEmpty:
            return dropped
        agent_queue.task_done()
        dropped += 1


async def dispatch_transcript(
    event: TranscriptEvent,
    agent_queue: "asyncio.Queue[AgentCommand]",
    metadata: Optional[dict] = None,
) -> None:
    """Forward finalized transcript events to the agent queue."""
    if event.type != "final":
        return

    text = canonicalize_command_text(event.text).strip()
    if not text:
        return

    source = str((metadata or {}).get("source") or event.source or "microphone")
    if should_suppress_transcripts(source):
        print(f"[transcription] suppressed final transcript during agent speech: {text!r}")
        return
    decision = should_execute_final_transcript(text, source)
    if not decision.should_execute:
        print(f"[transcription] dropped final transcript ({decision.reason}): {text!r}")
        return

    now = time.time()
    if _RECENT_FINAL["text"] == text and (now - _RECENT_FINAL["at"]) < 2.0:
        print(f"[transcription] dropped duplicate final transcript: {text!r}")
        return
    _RECENT_FINAL["text"] = text
    _RECENT_FINAL["at"] = now

    dropped = _drop_pending_commands(agent_queue)
    if dropped:
        print(f"[queue] replaced {dropped} pending command(s) with latest transcript")

    await agent_queue.put(
        AgentCommand(
            transcript_id=event.transcript_id,
            text=text,
            metadata={"source": source, **(metadata or {})},
        )
    )
