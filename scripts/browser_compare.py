#!/usr/bin/env python3
"""Compare the current repo browser agent against browser-use on the same task.

This script intentionally shells out to the two separate Python environments:
- .venv for the current app/runtime
- .venv-browseruse for browser-use experiments (Python 3.11+)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CURRENT_PYTHON = REPO_ROOT / ".venv" / "bin" / "python3"
BROWSER_USE_BIN = REPO_ROOT / ".venv-browseruse" / "bin" / "browser-use"


def _run(command: list[str], env: dict[str, str]) -> dict[str, Any]:
    start = time.perf_counter()
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    duration = time.perf_counter() - start
    return {
        "command": command,
        "returncode": result.returncode,
        "elapsed_seconds": round(duration, 2),
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def run_current_backend(task: str, env: dict[str, str]) -> dict[str, Any]:
    if not CURRENT_PYTHON.exists():
        return {
            "backend": "current",
            "ok": False,
            "error": f"Missing current app venv at {CURRENT_PYTHON}",
        }

    code = f"""
import asyncio
from src.agent.planner import execute_command
from src.shared.events import AgentCommand

command = AgentCommand(
    transcript_id='browser_compare',
    text={task!r},
)

print(asyncio.run(execute_command(command)))
"""
    outcome = _run([str(CURRENT_PYTHON), "-c", code], env)
    outcome["backend"] = "current"
    outcome["ok"] = outcome["returncode"] == 0
    return outcome


def run_browser_use_backend(
    task: str,
    env: dict[str, str],
    browser_mode: str,
    llm: str,
    max_steps: int,
) -> dict[str, Any]:
    if not BROWSER_USE_BIN.exists():
        return {
            "backend": "browser-use",
            "ok": False,
            "error": f"Missing browser-use env at {BROWSER_USE_BIN}",
        }

    command = [
        str(BROWSER_USE_BIN),
        "--json",
        "--browser",
        browser_mode,
        "run",
        task,
        "--llm",
        llm,
        "--max-steps",
        str(max_steps),
    ]
    outcome = _run(command, env)
    outcome["backend"] = "browser-use"
    outcome["ok"] = outcome["returncode"] == 0
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", help="Natural-language browser task to compare")
    parser.add_argument(
        "--backend",
        choices=["current", "browser-use", "both"],
        default="both",
        help="Which backend(s) to run",
    )
    parser.add_argument(
        "--browser-use-browser",
        choices=["chromium", "real", "remote"],
        default="real",
        help="browser-use browser mode",
    )
    parser.add_argument(
        "--browser-use-llm",
        default="claude-sonnet-4-20250514",
        help="browser-use LLM model name",
    )
    parser.add_argument(
        "--browser-use-max-steps",
        type=int,
        default=8,
        help="browser-use max steps",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON instead of a human-readable summary",
    )
    args = parser.parse_args()

    env = os.environ.copy()
    if not env.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is required for both backends.", file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    if args.backend in {"current", "both"}:
        results.append(run_current_backend(args.task, env))
    if args.backend in {"browser-use", "both"}:
        results.append(
            run_browser_use_backend(
                args.task,
                env,
                browser_mode=args.browser_use_browser,
                llm=args.browser_use_llm,
                max_steps=args.browser_use_max_steps,
            )
        )

    if args.json:
        print(json.dumps({"task": args.task, "results": results}, indent=2))
        return 0

    print(f"Task: {args.task}")
    for result in results:
        print("")
        print(f"[{result['backend']}] ok={result.get('ok')} elapsed={result.get('elapsed_seconds')}s returncode={result.get('returncode')}")
        if result.get("error"):
            print(result["error"])
            continue
        if result.get("stdout"):
            print("stdout:")
            print(result["stdout"])
        if result.get("stderr"):
            print("stderr:")
            print(result["stderr"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
