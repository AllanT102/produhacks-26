"""Dispatch finalized transcripts to the agent."""

import asyncio
from typing import Optional

from src.shared.events import AgentCommand, TranscriptEvent


async def dispatch_transcript(
    event: TranscriptEvent,
    agent_queue: "asyncio.Queue[AgentCommand]",
    metadata: Optional[dict] = None,
) -> None:
    """Forward finalized transcript events to the agent queue."""
    if event.type != "final":
        return

    text = event.text.strip()
    if not text:
        return

    await agent_queue.put(
        AgentCommand(
            transcript_id=event.transcript_id,
            text=text,
            metadata=metadata or {},
        )
    )
