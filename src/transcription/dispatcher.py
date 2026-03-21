"""Dispatch finalized transcripts to the agent."""

from src.shared.events import TranscriptEvent


def dispatch_transcript(event: TranscriptEvent) -> dict:
    """Return a simple handoff envelope for the planner."""
    return {
        "transcript_id": event.transcript_id,
        "text": event.text,
    }
