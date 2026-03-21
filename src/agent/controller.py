"""Control plane for agent execution."""

import asyncio
from typing import Optional


class AgentController:
    """Track and interrupt in-flight agent work."""

    def __init__(self) -> None:
        self._cancel_event = asyncio.Event()
        self._current_task: Optional[asyncio.Task] = None

    def request_stop(self) -> None:
        """Signal that current LLM work should stop."""
        self._cancel_event.set()
        if self._current_task is not None and not self._current_task.done():
            self._current_task.cancel()

    def reset(self) -> None:
        """Clear any previous stop request before processing new work."""
        self._cancel_event = asyncio.Event()

    def set_current_task(self, task: Optional[asyncio.Task]) -> None:
        """Track the currently active agent task."""
        self._current_task = task

    @property
    def cancel_event(self) -> asyncio.Event:
        """Expose the current cancellation event."""
        return self._cancel_event
