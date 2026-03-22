#!/usr/bin/env python3
"""Persistent browser-use server for fast repeated browser commands."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.browser_use_direct import build_browser, run_best_effort_command_in_browser


def _suppress_logs() -> None:
    logging.basicConfig(level=logging.CRITICAL, force=True)
    for name in (
        "browser_use",
        "BrowserSession",
        "utils",
        "asyncio",
    ):
        logging.getLogger(name).setLevel(logging.CRITICAL)


async def _handle_request(browser, payload: dict[str, Any]) -> dict[str, Any]:
    request_id = payload.get("id")
    command = str(payload.get("command") or "").strip()
    if not command:
        return {"id": request_id, "success": False, "error": "Missing command"}

    try:
        result = await run_best_effort_command_in_browser(command, browser)
        return {"id": request_id, **result}
    except Exception as exc:
        return {"id": request_id, "success": False, "error": str(exc), "command": command}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-directory", default="Default")
    args = parser.parse_args()

    _suppress_logs()

    browser = build_browser(args.profile_directory)
    await browser.start()
    print(
        json.dumps(
            {
                "event": "ready",
                "profile_directory": args.profile_directory,
                "mode": "cdp" if os.getenv("BROWSER_USE_CDP_URL") else "system_chrome",
                "cdp_url": os.getenv("BROWSER_USE_CDP_URL", ""),
            }
        ),
        flush=True,
    )

    try:
        while True:
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            try:
                payload = json.loads(line)
            except Exception:
                print(json.dumps({"success": False, "error": "Invalid JSON request"}), flush=True)
                continue

            if payload.get("shutdown"):
                print(json.dumps({"event": "shutdown"}), flush=True)
                break

            response = await _handle_request(browser, payload)
            print(json.dumps(response), flush=True)
    finally:
        await browser.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
