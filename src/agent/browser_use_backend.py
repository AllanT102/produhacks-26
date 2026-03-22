"""Browser-only backend powered by browser-use in a separate Python environment."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from src.shared.events import AgentCommand
from src.shared.timing import elapsed_ms
from src.tool_runtime.tools.browser import browser_get_page

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PYTHON = _REPO_ROOT / ".venv-browseruse" / "bin" / "python"
_SERVER_SCRIPT = _REPO_ROOT / "scripts" / "browser_use_server.py"
_SERVER_TIMEOUT_SECONDS = float(os.getenv("BROWSER_USE_TIMEOUT", "45"))

_SERVER_PROCESS: Optional[asyncio.subprocess.Process] = None
_SERVER_LOCK = asyncio.Lock()

_BROWSER_HINTS = (
    "browser",
    "chrome",
    "google chrome",
    "youtube",
    "linkedin",
    "website",
    "web page",
    "webpage",
    "tab",
    ".com",
    ".org",
    ".io",
)

_DESKTOP_HINTS = (
    "finder",
    "folder",
    "file",
    "desktop",
    "dock",
    "slack",
    "terminal",
    "ghostty",
    "brightness",
    "volume",
)

_BROWSER_ACTION_HINTS = (
    "open",
    "go to",
    "search",
    "scroll",
    "click",
    "subscribe",
    "follow",
    "type",
    "find",
    "play",
    "pause",
)


def browser_use_python() -> Path:
    override = os.getenv("BROWSER_USE_PYTHON")
    if override:
        return Path(override).expanduser()
    return _DEFAULT_PYTHON


def browser_use_available() -> bool:
    return browser_use_python().exists() and _SERVER_SCRIPT.exists()


def should_use_browser_use(command: AgentCommand) -> bool:
    if os.getenv("BROWSER_USE_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        return False
    if not browser_use_available():
        return False

    text = command.text.strip().lower()
    if not text:
        return False

    if any(hint in text for hint in _DESKTOP_HINTS) and not any(hint in text for hint in _BROWSER_HINTS):
        return False
    if any(hint in text for hint in _BROWSER_HINTS):
        return True

    if any(hint in text for hint in _BROWSER_ACTION_HINTS):
        page = browser_get_page()
        if page.get("ok") and "chrome" not in str(page.get("error", "")).lower():
            return True

    return False


def _extract_browser_use_summary(payload: dict[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("final_result", "result", "answer", "message", "summary", "text"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        if data:
            return json.dumps(data)
    for key in ("summary", "result", "answer", "message", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if isinstance(data, str) and data.strip():
        return data.strip()
    if isinstance(payload.get("message"), str) and payload["message"].strip():
        return payload["message"].strip()
    return "Completed browser task with browser-use."


def _browser_use_task_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


def _parse_browser_use_payload(stdout: str) -> Optional[dict[str, Any]]:
    for line in reversed([line.strip() for line in stdout.splitlines() if line.strip()]):
        try:
            candidate = json.loads(line)
        except Exception:
            continue
        if isinstance(candidate, dict):
            return candidate

    try:
        candidate = json.loads(stdout)
    except Exception:
        candidate = None
    if isinstance(candidate, dict):
        return candidate

    match = re.search(r"(\{.*\})", stdout, re.DOTALL)
    if not match:
        return None
    try:
        candidate = json.loads(match.group(1))
    except Exception:
        return None
    return candidate if isinstance(candidate, dict) else None


async def execute_command_with_browser_use(command: AgentCommand) -> str:
    """Execute a browser task through browser-use and return a concise summary."""
    started_at = time.perf_counter()
    if not browser_use_available():
        raise RuntimeError(f"browser-use server not available at {browser_use_python()} and {_SERVER_SCRIPT}")

    async with _SERVER_LOCK:
        process = await _ensure_browser_use_server_locked()
        response = await _send_browser_use_request_locked(process, command.text)

    task_payload = _browser_use_task_payload(response)
    if response.get("success") is False or task_payload.get("success") is False:
        message = response.get("error") or response.get("message") or "browser-use task failed"
        raise RuntimeError(str(message))
    print("[timing] browser-use execute total took {:.1f}ms".format(elapsed_ms(started_at)))
    return _extract_browser_use_summary(task_payload)


async def _ensure_browser_use_server_locked() -> asyncio.subprocess.Process:
    global _SERVER_PROCESS

    if _SERVER_PROCESS is not None and _SERVER_PROCESS.returncode is None:
        return _SERVER_PROCESS

    cli = [
        str(browser_use_python()),
        str(_SERVER_SCRIPT),
        "--profile-directory",
        os.getenv("BROWSER_USE_PROFILE", "Default"),
    ]
    process = await asyncio.create_subprocess_exec(
        *cli,
        cwd=str(_REPO_ROOT),
        env=os.environ.copy(),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    try:
        ready_started_at = time.perf_counter()
        ready = await _read_browser_use_json_line(process, _SERVER_TIMEOUT_SECONDS)
        print("[timing] browser-use server startup took {:.1f}ms".format(elapsed_ms(ready_started_at)))
    except Exception:
        process.kill()
        await process.wait()
        raise

    if ready.get("event") != "ready":
        process.kill()
        await process.wait()
        raise RuntimeError(f"browser-use server failed to start: {ready}")

    _SERVER_PROCESS = process
    return process


async def _send_browser_use_request_locked(
    process: asyncio.subprocess.Process,
    command_text: str,
) -> dict[str, Any]:
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("browser-use server pipes are not available")

    request_id = uuid4().hex
    request = {"id": request_id, "command": command_text}
    process.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
    await process.stdin.drain()

    while True:
        response = await _read_browser_use_json_line(process, _SERVER_TIMEOUT_SECONDS)
        if response.get("id") == request_id:
            return response


async def _read_browser_use_json_line(
    process: asyncio.subprocess.Process,
    timeout_seconds: float,
) -> dict[str, Any]:
    if process.stdout is None:
        raise RuntimeError("browser-use server stdout is not available")

    while True:
        try:
            raw = await asyncio.wait_for(process.stdout.readline(), timeout=timeout_seconds)
        except asyncio.TimeoutError as exc:
            await _stop_browser_use_server_locked(process)
            raise RuntimeError("browser-use server timed out") from exc

        if not raw:
            returncode = await process.wait()
            global _SERVER_PROCESS
            if _SERVER_PROCESS is process:
                _SERVER_PROCESS = None
            raise RuntimeError(f"browser-use server exited unexpectedly with code {returncode}")

        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue

        try:
            payload = json.loads(line)
        except Exception:
            continue

        if isinstance(payload, dict):
            return payload


async def _stop_browser_use_server_locked(process: asyncio.subprocess.Process) -> None:
    global _SERVER_PROCESS
    if process.stdin is not None and process.returncode is None:
        try:
            process.stdin.write(b'{"shutdown": true}\n')
            await process.stdin.drain()
        except Exception:
            pass
    if process.returncode is None:
        try:
            await asyncio.wait_for(process.wait(), timeout=2)
        except Exception:
            process.kill()
            await process.wait()
    if _SERVER_PROCESS is process:
        _SERVER_PROCESS = None
