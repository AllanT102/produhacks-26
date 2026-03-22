"""Run local planner experiments against a deterministic mock executor."""

from __future__ import annotations

import argparse
import asyncio
import uuid

from src.agent.mock_executor import MockExecutor
from src.agent.planner import execute_command_with_tools
from src.shared.events import AgentCommand


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run planner experiments with mocked tools.")
    parser.add_argument(
        "--scenario",
        choices=["youtube_search", "youtube_open_first"],
        default="youtube_search",
        help="Mock screen scenario to run.",
    )
    parser.add_argument(
        "--goal",
        required=True,
        help="User command to give to the planner.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=12,
        help="Maximum planner iterations.",
    )
    return parser


async def _main() -> None:
    args = _build_parser().parse_args()
    executor = MockExecutor(args.scenario)
    command = AgentCommand(
        transcript_id=f"exp_{uuid.uuid4().hex[:8]}",
        text=args.goal,
        metadata={"scenario": args.scenario},
    )

    summary = await execute_command_with_tools(
        command,
        executor.execute,
        profile_name="fast",
        model="claude-sonnet-4-20250514",
        max_tokens=700,
        max_iterations=args.max_iterations,
    )

    print("\n[experiment] summary={}".format(summary))
    print("[experiment] scenario={}".format(args.scenario))
    print("[experiment] tool_history={}".format(executor.state.history))


if __name__ == "__main__":
    asyncio.run(_main())
