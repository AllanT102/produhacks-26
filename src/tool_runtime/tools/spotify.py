"""Spotify control tools via AppleScript."""

import subprocess
import time


def _osascript(script: str) -> dict:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=True,
        )
        return {"ok": True, "output": result.stdout.strip()}
    except subprocess.CalledProcessError as exc:
        return {"ok": False, "error": exc.stderr.strip() or str(exc)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _osascript_multiline(script: str) -> dict:
    try:
        result = subprocess.run(
            ["osascript"],
            input=script,
            capture_output=True,
            text=True,
            check=True,
        )
        return {"ok": True, "output": result.stdout.strip()}
    except subprocess.CalledProcessError as exc:
        return {"ok": False, "error": exc.stderr.strip() or str(exc)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def spotify_play(query: str) -> dict:
    """Play a Spotify track from a plain-text query via AppleScript."""
    safe_query = query.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
tell application "Spotify"
    activate
    play track "{safe_query}"
end tell
'''
    subprocess.run(["open", "-a", "Spotify"], check=False)
    time.sleep(0.8)
    result = _osascript_multiline(script)
    if not result["ok"]:
        return result
    return {"ok": True, "query": query, "method": "play track"}


def spotify_pause() -> dict:
    """Pause Spotify playback."""
    return _osascript('tell application "Spotify" to pause')


def spotify_resume() -> dict:
    """Resume Spotify playback."""
    return _osascript('tell application "Spotify" to play')


def spotify_next() -> dict:
    """Skip to the next track in Spotify."""
    return _osascript('tell application "Spotify" to next track')


def spotify_previous() -> dict:
    """Go back to the previous track in Spotify."""
    return _osascript('tell application "Spotify" to previous track')


def spotify_get_current_track() -> dict:
    """Return the currently playing track and artist from Spotify."""
    script = """
tell application "Spotify"
    set trackName to name of current track
    set artistName to artist of current track
    set albumName to album of current track
    set playerState to player state as string
    return trackName & " | " & artistName & " | " & albumName & " | " & playerState
end tell
"""
    result = _osascript(script)
    if not result["ok"]:
        return result
    parts = [p.strip() for p in result["output"].split("|")]
    if len(parts) >= 4:
        return {
            "ok": True,
            "track": parts[0],
            "artist": parts[1],
            "album": parts[2],
            "state": parts[3],
        }
    return {"ok": True, "raw": result["output"]}
