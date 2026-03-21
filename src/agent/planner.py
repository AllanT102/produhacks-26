"""Planner entry points for turning transcripts into tool calls."""


def plan_from_transcript(text: str) -> dict:
    """Return a minimal plan structure for a transcript."""
    normalized = text.strip()
    return {
        "goal": normalized,
        "steps": [
            {
                "type": "reason",
                "status": "pending",
                "description": "Interpret transcript and choose the next tool call.",
            }
        ],
    }
