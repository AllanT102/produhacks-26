"""Volume tool."""

import subprocess


STEP_SIZE = 10  # volume units per step (0–100 scale)


def _get_volume() -> int:
    result = subprocess.run(
        ["osascript", "-e", "output volume of (get volume settings)"],
        capture_output=True, text=True, check=True,
    )
    return int(result.stdout.strip())


def set_volume(action: str, steps: int = 1) -> dict:
    """
    Adjust system volume.

    Args:
        action: "up", "down", "mute", or "unmute"
        steps:  Number of increments to raise/lower (only used for up/down).
    """
    try:
        if action == "mute":
            subprocess.run(["osascript", "-e", "set volume output muted true"], check=True)
            return {"ok": True, "action": "mute"}

        if action == "unmute":
            subprocess.run(["osascript", "-e", "set volume output muted false"], check=True)
            return {"ok": True, "action": "unmute"}

        if action in ("up", "down"):
            current = _get_volume()
            delta = steps * STEP_SIZE
            new_level = current + delta if action == "up" else current - delta
            new_level = max(0, min(100, new_level))
            subprocess.run(
                ["osascript", "-e", f"set volume output volume {new_level}"],
                check=True,
            )
            return {"ok": True, "action": action, "steps": steps, "level": new_level}

        return {"ok": False, "error": f"action must be 'up', 'down', 'mute', or 'unmute', got '{action}'"}

    except Exception as exc:
        return {"ok": False, "error": str(exc)}
