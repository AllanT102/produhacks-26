"""Speech output helpers and transcript suppression state."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

_INTERACTIVE_SOURCES = {"typed", "wispr", "fake_transcript"}
_DEFAULT_COOLDOWN_SECONDS = float(os.getenv("AGENT_SPEECH_COOLDOWN_SECONDS", "1.0"))
_DEFAULT_RATE = int(os.getenv("AGENT_TTS_RATE", "215"))
_DEFAULT_VOICE = os.getenv("AGENT_TTS_VOICE", "").strip()
_DEFAULT_PROVIDER = os.getenv("AGENT_TTS_PROVIDER", "auto").strip().lower() or "auto"
_ELEVENLABS_BASE_URL = os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io").rstrip("/")
_ELEVENLABS_TTS_MODEL_ID = os.getenv("ELEVENLABS_TTS_MODEL_ID", "eleven_multilingual_v2").strip()
_ELEVENLABS_TTS_OUTPUT_FORMAT = os.getenv("ELEVENLABS_TTS_OUTPUT_FORMAT", "mp3_44100_128").strip()
_ELEVENLABS_TTS_LANGUAGE_CODE = os.getenv("ELEVENLABS_TTS_LANGUAGE_CODE", "en").strip()
_ELEVENLABS_TTS_VOICE_ID = os.getenv("ELEVENLABS_TTS_VOICE_ID", "").strip()
_ELEVENLABS_TTS_VOICE_NAME = os.getenv("ELEVENLABS_TTS_VOICE_NAME", "River").strip()
_ELEVENLABS_TTS_SPEED = os.getenv("ELEVENLABS_TTS_SPEED", "1.12").strip()
_ELEVENLABS_STREAMING_LATENCY = os.getenv("ELEVENLABS_TTS_OPTIMIZE_STREAMING_LATENCY", "").strip()
_VOICE_CACHE_LOCK = threading.Lock()
_VOICE_CACHE: dict[str, dict[str, str]] = {}


class _SpeechState:
    """Track whether the agent is actively speaking or has just finished."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_count = 0
        self._suppress_until = 0.0

    def begin(self) -> None:
        with self._lock:
            self._active_count += 1
            self._suppress_until = 0.0

    def end(self, cooldown_seconds: float) -> None:
        with self._lock:
            self._active_count = max(0, self._active_count - 1)
            if self._active_count == 0:
                self._suppress_until = max(self._suppress_until, time.time() + cooldown_seconds)

    def should_suppress_transcripts(self, source: str) -> bool:
        if source in _INTERACTIVE_SOURCES:
            return False
        with self._lock:
            if self._active_count > 0:
                return True
            return time.time() < self._suppress_until


_SPEECH_STATE = _SpeechState()


@dataclass(frozen=True)
class SpeechResult:
    """Reported details for a completed speech action."""

    text: str
    voice: str
    rate: int
    provider: str


def should_suppress_transcripts(source: str) -> bool:
    """Return whether live transcription should be ignored during agent speech."""
    return _SPEECH_STATE.should_suppress_transcripts(str(source or "").strip().lower())


def prepare_speech_text(text: str) -> str:
    """Normalize extracted page text into something comfortable for TTS."""
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    normalized = normalized.replace("•", ". ")
    normalized = normalized.replace("·", ". ")
    normalized = normalized.replace("…", ". ")
    normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalized)
    normalized = re.sub(r"([.!?])([A-Z])", r"\1 \2", normalized)
    return normalized.strip()


def _elevenlabs_api_key() -> str:
    return os.getenv("ELEVENLABS_API_KEY", "").strip()


def _should_use_elevenlabs(provider: str) -> bool:
    if provider == "elevenlabs":
        return True
    if provider == "say":
        return False
    return bool(_elevenlabs_api_key())


def _elevenlabs_headers() -> dict[str, str]:
    api_key = _elevenlabs_api_key()
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is required for ElevenLabs speech output.")
    return {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }


def _http_json_sync(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"xi-api-key": _elevenlabs_api_key()})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(body or f"ElevenLabs request failed with HTTP {exc.code}.") from exc


def _score_voice(voice: dict[str, Any]) -> int:
    labels = voice.get("labels") or {}
    score = 0
    if voice.get("category") == "premade":
        score += 20
    if str(labels.get("language") or "").lower() == "en":
        score += 40
    use_case = str(labels.get("use_case") or "").lower()
    if use_case == "conversational":
        score += 30
    elif use_case == "informative_educational":
        score += 26
    elif use_case == "narrative_story":
        score += 18
    descriptive = str(labels.get("descriptive") or "").lower()
    if "calm" in descriptive:
        score += 22
    if "professional" in descriptive:
        score += 16
    if "neutral" in descriptive:
        score += 16
    if "classy" in descriptive:
        score += 8
    return score


def _choose_voice(voices: list[dict[str, Any]]) -> dict[str, str]:
    if not voices:
        raise RuntimeError("No ElevenLabs voices are available for this account.")

    configured_name = _ELEVENLABS_TTS_VOICE_NAME.lower()
    if _ELEVENLABS_TTS_VOICE_ID:
        for voice in voices:
            if str(voice.get("voice_id") or "").strip() == _ELEVENLABS_TTS_VOICE_ID:
                return {
                    "voice_id": str(voice.get("voice_id") or ""),
                    "voice_name": str(voice.get("name") or _ELEVENLABS_TTS_VOICE_ID),
                }
        raise RuntimeError(f"Configured ElevenLabs voice id was not found: {_ELEVENLABS_TTS_VOICE_ID}")

    for voice in voices:
        name = str(voice.get("name") or "")
        lower = name.lower()
        if configured_name and (lower == configured_name or lower.startswith(configured_name)):
            return {"voice_id": str(voice.get("voice_id") or ""), "voice_name": name}

    preferred_prefixes = (
        configured_name,
        "river",
        "sarah",
        "matilda",
        "roger",
        "alice",
    )
    for prefix in preferred_prefixes:
        if not prefix:
            continue
        for voice in voices:
            name = str(voice.get("name") or "")
            if name.lower().startswith(prefix):
                return {"voice_id": str(voice.get("voice_id") or ""), "voice_name": name}

    best = max(voices, key=_score_voice)
    return {
        "voice_id": str(best.get("voice_id") or ""),
        "voice_name": str(best.get("name") or best.get("voice_id") or "default"),
    }


def _resolve_elevenlabs_voice_sync() -> dict[str, str]:
    cache_key = "|".join([_ELEVENLABS_TTS_VOICE_ID, _ELEVENLABS_TTS_VOICE_NAME, _elevenlabs_api_key()[:12]])
    with _VOICE_CACHE_LOCK:
        cached = _VOICE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    payload = _http_json_sync(f"{_ELEVENLABS_BASE_URL}/v1/voices")
    voices = payload.get("voices")
    if not isinstance(voices, list):
        raise RuntimeError("ElevenLabs voices response was missing the voices list.")
    chosen = _choose_voice([voice for voice in voices if isinstance(voice, dict)])
    with _VOICE_CACHE_LOCK:
        _VOICE_CACHE[cache_key] = chosen
    return chosen


def _elevenlabs_voice_settings() -> Optional[dict[str, Any]]:
    settings: dict[str, Any] = {}
    env_map = {
        "stability": os.getenv("ELEVENLABS_TTS_STABILITY"),
        "similarity_boost": os.getenv("ELEVENLABS_TTS_SIMILARITY_BOOST"),
        "style": os.getenv("ELEVENLABS_TTS_STYLE"),
        "speed": _ELEVENLABS_TTS_SPEED,
    }
    for key, raw in env_map.items():
        if raw is None or not raw.strip():
            continue
        settings[key] = float(raw)
    speaker_boost = os.getenv("ELEVENLABS_TTS_USE_SPEAKER_BOOST")
    if speaker_boost is not None and speaker_boost.strip():
        settings["use_speaker_boost"] = speaker_boost.strip().lower() not in {"0", "false", "no", "off"}
    return settings or None


class _ElevenLabsSynthesisJob:
    """Download ElevenLabs audio with best-effort cancellation support."""

    def __init__(self, text: str, voice_id: str) -> None:
        self.text = text
        self.voice_id = voice_id
        self._cancelled = threading.Event()
        self._response_lock = threading.Lock()
        self._response = None
        self._temp_path: Optional[Path] = None

    def cancel(self) -> None:
        self._cancelled.set()
        with self._response_lock:
            response = self._response
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        if self._temp_path is not None:
            self._temp_path.unlink(missing_ok=True)

    def run(self) -> Path:
        query: dict[str, str] = {"output_format": _ELEVENLABS_TTS_OUTPUT_FORMAT}
        if _ELEVENLABS_STREAMING_LATENCY:
            query["optimize_streaming_latency"] = _ELEVENLABS_STREAMING_LATENCY
        url = "{}{}?{}".format(
            _ELEVENLABS_BASE_URL,
            f"/v1/text-to-speech/{self.voice_id}/stream",
            urllib.parse.urlencode(query),
        )
        payload: dict[str, Any] = {
            "text": self.text,
            "model_id": _ELEVENLABS_TTS_MODEL_ID,
        }
        if _ELEVENLABS_TTS_LANGUAGE_CODE:
            payload["language_code"] = _ELEVENLABS_TTS_LANGUAGE_CODE
        voice_settings = _elevenlabs_voice_settings()
        if voice_settings is not None:
            payload["voice_settings"] = voice_settings

        request = urllib.request.Request(
            url,
            headers=_elevenlabs_headers(),
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )

        suffix = ".mp3" if _ELEVENLABS_TTS_OUTPUT_FORMAT.startswith("mp3") else ".wav"
        temp_file = tempfile.NamedTemporaryFile(prefix="codex-tts-", suffix=suffix, delete=False)
        temp_path = Path(temp_file.name)
        temp_file.close()
        self._temp_path = temp_path

        try:
            with urllib.request.urlopen(request, timeout=60) as response, temp_path.open("wb") as handle:
                with self._response_lock:
                    self._response = response
                while True:
                    if self._cancelled.is_set():
                        raise RuntimeError("Speech synthesis cancelled.")
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                if self._cancelled.is_set():
                    raise RuntimeError("Speech synthesis cancelled.")
                return temp_path
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(body or f"ElevenLabs speech synthesis failed with HTTP {exc.code}.") from exc
        finally:
            with self._response_lock:
                self._response = None
            if self._cancelled.is_set():
                temp_path.unlink(missing_ok=True)


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=1.0)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


async def _play_audio_file(path: Path) -> None:
    afplay_bin = shutil.which("afplay")
    if not afplay_bin:
        raise RuntimeError("macOS audio playback is unavailable because the `afplay` command was not found.")
    process = await asyncio.create_subprocess_exec(
        afplay_bin,
        str(path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await process.communicate()
    except asyncio.CancelledError:
        await _terminate_process(process)
        raise
    if process.returncode != 0:
        message = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(message or "Audio playback failed.")


async def _speak_with_say(
    spoken_text: str,
    *,
    voice: Optional[str],
    rate: int,
) -> SpeechResult:
    say_bin = shutil.which("say")
    if not say_bin:
        raise RuntimeError("macOS text-to-speech is unavailable because the `say` command was not found.")

    resolved_voice = (voice or _DEFAULT_VOICE).strip()
    command = [say_bin, "-r", str(rate)]
    if resolved_voice:
        command.extend(["-v", resolved_voice])

    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await process.communicate(spoken_text.encode("utf-8"))
    except asyncio.CancelledError:
        await _terminate_process(process)
        raise

    if process.returncode != 0:
        message = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(message or "macOS text-to-speech failed.")

    return SpeechResult(
        text=spoken_text,
        voice=resolved_voice or "default",
        rate=rate,
        provider="say",
    )


async def _speak_with_elevenlabs(spoken_text: str) -> SpeechResult:
    voice = await asyncio.to_thread(_resolve_elevenlabs_voice_sync)
    audio_path: Optional[Path] = None
    synthesis_job: Optional[_ElevenLabsSynthesisJob] = None
    synthesis_task: Optional[asyncio.Task[Path]] = None
    try:
        synthesis_job = _ElevenLabsSynthesisJob(spoken_text, voice["voice_id"])
        synthesis_task = asyncio.create_task(asyncio.to_thread(synthesis_job.run))
        try:
            audio_path = await synthesis_task
        except asyncio.CancelledError:
            synthesis_job.cancel()
            if synthesis_task is not None:
                synthesis_task.cancel()
            raise
        await _play_audio_file(audio_path)
    finally:
        if synthesis_job is not None:
            synthesis_job.cancel()
        if audio_path is not None:
            audio_path.unlink(missing_ok=True)

    return SpeechResult(
        text=spoken_text,
        voice=voice["voice_name"],
        rate=0,
        provider="elevenlabs",
    )


async def speak_text(
    text: str,
    *,
    voice: Optional[str] = None,
    rate: Optional[int] = None,
    cooldown_seconds: Optional[float] = None,
) -> SpeechResult:
    """Speak text aloud, preferring ElevenLabs when configured."""
    spoken_text = prepare_speech_text(text)
    if not spoken_text:
        raise RuntimeError("Nothing to read aloud from the page.")

    resolved_rate = int(rate or _DEFAULT_RATE)
    resolved_cooldown = _DEFAULT_COOLDOWN_SECONDS if cooldown_seconds is None else float(cooldown_seconds)
    provider = _DEFAULT_PROVIDER
    if provider not in {"auto", "elevenlabs", "say"}:
        provider = "auto"

    _SPEECH_STATE.begin()
    try:
        if _should_use_elevenlabs(provider):
            result = await _speak_with_elevenlabs(spoken_text)
        else:
            result = await _speak_with_say(spoken_text, voice=voice, rate=resolved_rate)
    finally:
        _SPEECH_STATE.end(resolved_cooldown)

    return result
