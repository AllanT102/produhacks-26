"""browser-use powered agentic planner."""

import asyncio
from pathlib import Path
from typing import Callable, Optional

from browser_use import Agent
from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession
from browser_use.llm.anthropic.chat import ChatAnthropic

from src.shared.events import AgentCommand

_MODEL = "claude-opus-4-5"
_SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.md"

_BROWSER_PROFILE = BrowserProfile(
    user_data_dir=Path.home() / ".config" / "produhacks" / "chrome-profile",
    keep_alive=True,
    headless=False,
)

# Single shared session — all commands continue from the same tab/page state.
_SESSION: BrowserSession | None = None


def _get_session() -> BrowserSession:
    global _SESSION
    if _SESSION is None:
        _SESSION = BrowserSession(browser_profile=_BROWSER_PROFILE)
    return _SESSION


def _build_task(text: str) -> str:
    template = _SYSTEM_PROMPT_PATH.read_text()
    return template.replace("[user prompt]", text)


async def execute_command(command: AgentCommand, on_step: Optional[Callable[[str], None]] = None) -> str:
    """Run browser-use Agent for a single voice command."""
    llm = ChatAnthropic(model=_MODEL)

    step_cb = None
    if on_step is not None:
        async def step_cb(_browser_state, output, _step_num):
            try:
                text = output.next_goal or output.evaluation_previous_goal or ""
                if text:
                    on_step(text)
            except Exception:
                pass

    agent = Agent(
        task=_build_task(command.text),
        llm=llm,
        browser_session=_get_session(),
        register_new_step_callback=step_cb,
    )
    try:
        result = await agent.run()
    except asyncio.CancelledError:
        agent.stop()
        raise
    return result.final_result() or "Done."
