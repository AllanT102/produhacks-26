"""Planner entry points for turning transcripts into tool calls."""


def plan_from_transcript(text: str) -> dict:
    """Return a placeholder plan structure for a transcript."""
    return {
        "goal": text,
        "steps": [],
    }
