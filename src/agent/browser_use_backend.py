"""Browser-use backend: runs all commands directly through the browser-use Agent."""

from __future__ import annotations

import os
import time

from src.shared.events import AgentCommand
from src.shared.timing import elapsed_ms


def browser_use_available() -> bool:
    try:
        import browser_use  # noqa: F401
        return True
    except ImportError:
        return False


def should_use_browser_use(command: AgentCommand) -> bool:
    if os.getenv("BROWSER_USE_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        return False
    return browser_use_available()


async def execute_command_with_browser_use(command: AgentCommand) -> str:
    """Execute a browser task using the browser-use Agent and return a summary."""
    from browser_use import Agent, Browser
    from browser_use.llm.anthropic.chat import ChatAnthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    llm = ChatAnthropic(
        model=os.getenv("BROWSER_USE_MODEL", "claude-sonnet-4-20250514"),
        api_key=api_key,
    )

    cdp_url = os.getenv("BROWSER_USE_CDP_URL", "").strip()
    if cdp_url:
        browser = Browser(cdp_url=cdp_url, keep_alive=True)
    else:
        browser = Browser.from_system_chrome(
            profile_directory=os.getenv("BROWSER_USE_PROFILE", "Default"),
            keep_alive=True,
        )

    agent = Agent(
        task=command.text,
        llm=llm,
        browser=browser,
    )

    started_at = time.perf_counter()
    print(f"[browser-use] running agent for task={command.text!r}")
    result = await agent.run()
    print("[timing] browser-use agent took {:.1f}ms".format(elapsed_ms(started_at)))

    summary = result.final_result()
    return summary or f"Completed: {command.text}"
