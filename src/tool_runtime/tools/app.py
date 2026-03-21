"""App launcher tool."""

import subprocess


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


def open_app(app: str) -> dict:
    """
    Open an application by name.

    Args:
        app: App name or alias (e.g. "chrome", "Spotify", "discord")
    """
    resolved = ALIASES.get(app.lower(), app)
    try:
        subprocess.run(["open", "-a", resolved], check=True)
        return {"ok": True, "app": resolved}
    except subprocess.CalledProcessError:
        return {"ok": False, "error": f"Could not open '{resolved}' — is it installed?"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
