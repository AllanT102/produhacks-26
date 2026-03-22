"""Run local browser-use experiments against the current live browser backend."""

from __future__ import annotations

import argparse
import asyncio
import uuid

from src.agent.planner import execute_command
from src.shared.events import AgentCommand


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run browser-use planner experiments.")
    parser.add_argument(
        "--scenario",
        choices=["youtube_search", "youtube_open_first"],
        default="youtube_search",
        help="Legacy option retained for compatibility; ignored in browser-use mode.",
    )
    parser.add_argument(
        "--goal",
        required=True,
        help="User command to give to the planner.",
    )
    return parser


async def _main() -> None:
    args = _build_parser().parse_args()
    command = AgentCommand(
        transcript_id=f"exp_{uuid.uuid4().hex[:8]}",
        text=args.goal,
        metadata={"scenario": args.scenario},
    )

    summary = await execute_command(command)

    print("\n[experiment] summary={}".format(summary))
    print("[experiment] scenario={}".format(args.scenario))


if __name__ == "__main__":
    asyncio.run(_main())
