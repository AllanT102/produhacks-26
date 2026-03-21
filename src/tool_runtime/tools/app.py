"""App launcher tool."""

import subprocess
from typing import Optional


# Common app name aliases so the agent can use natural names
ALIASES: dict[str, str] = {
    "chrome": "Google Chrome",
    "spotify": "Spotify",
    "discord": "Discord",
    "safari": "Safari",
    "firefox": "Firefox",
    "slack": "Slack",
    "vscode": "Visual Studio Code",
    "code": "Visual Studio Code",
    "terminal": "Terminal",
    "finder": "Finder",
    "notes": "Notes",
    "mail": "Mail",
    "calendar": "Calendar",
    "youtube": "Google Chrome",
}


def open_app(app: str, url: Optional[str] = None) -> dict:
    """
    Open an application by name, optionally with a URL.

    Args:
        app: App name or alias (e.g. "chrome", "Spotify", "discord")
        url: Optional URL to open with the app
    """
    resolved = ALIASES.get(app.lower(), app)
    try:
        cmd = ["open", "-a", resolved]
        if url:
            cmd.append(url)
        subprocess.run(cmd, check=True)
        result = {"ok": True, "app": resolved}
        if url:
            result["url"] = url
        return result
    except subprocess.CalledProcessError:
        if url:
            return {"ok": False, "error": f"Could not open '{resolved}' with '{url}' — is it installed?"}
        return {"ok": False, "error": f"Could not open '{resolved}' — is it installed?"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
