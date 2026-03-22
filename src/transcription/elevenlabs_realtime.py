"""Realtime ElevenLabs speech-to-text transcription service."""

import asyncio
import base64
import itertools
import json
import os
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional
from urllib.parse import urlencode

from src.shared.events import TranscriptEvent
from src.transcription.dispatcher import dispatch_transcript
from src.transcription.mic_capture import AudioChunk, SoundDeviceMicrophone

TranscriptCallback = Callable[[TranscriptEvent], Awaitable[None]]


@dataclass
class ElevenLabsRealtimeConfig:
    """Tune the ElevenLabs realtime websocket session."""

    model_id: str = "scribe_v2_realtime"
    language_code: str = "en"
    include_timestamps: bool = False
    include_language_detection: bool = False
    commit_strategy: str = "vad"
    vad_silence_threshold_secs: float = 0.7
    vad_threshold: float = 0.45
    min_speech_duration_ms: int = 120
    min_silence_duration_ms: int = 160
    previous_text: str = ""
    endpoint: str = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"


class ElevenLabsRealtimeTranscriptionService:
    """Stream mic audio to ElevenLabs and emit partial/final transcript events."""

    def __init__(
        self,
        microphone: SoundDeviceMicrophone,
        agent_queue: "asyncio.Queue",
        config: Optional[ElevenLabsRealtimeConfig] = None,
        on_event: Optional[TranscriptCallback] = None,
    ) -> None:
        self.microphone = microphone
        self.agent_queue = agent_queue
        self.config = config or ElevenLabsRealtimeConfig()
        self.on_event = on_event
        self._running = False
        self._utterance_counter = itertools.count(1)
        self._current_transcript_id = self._next_transcript_id()
        self._sent_previous_text = False

    async def start(self) -> None:
        """Open a realtime websocket session and stream audio forever."""
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError(
                "websockets is required for ElevenLabs realtime transcription. Install requirements.txt first."
            ) from exc

        api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is required for ElevenLabs realtime transcription.")

        self.microphone.start()
        self._running = True
        reconnect_delay = 1.0
        params = {
            "model_id": self.config.model_id,
            "audio_format": "pcm_16000",
            "commit_strategy": self.config.commit_strategy,
            "vad_silence_threshold_secs": self.config.vad_silence_threshold_secs,
            "vad_threshold": self.config.vad_threshold,
            "min_speech_duration_ms": self.config.min_speech_duration_ms,
            "min_silence_duration_ms": self.config.min_silence_duration_ms,
            "include_timestamps": str(self.config.include_timestamps).lower(),
            "include_language_detection": str(self.config.include_language_detection).lower(),
        }
        if self.config.language_code:
            params["language_code"] = self.config.language_code
        url = "{}?{}".format(self.config.endpoint, urlencode(params))

        try:
            while self._running:
                try:
                    async with websockets.connect(
                        url,
                        additional_headers={"xi-api-key": api_key},
                        ping_interval=20,
                        ping_timeout=20,
                        max_size=None,
                    ) as websocket:
                        reconnect_delay = 1.0  # reset on successful connection
                        sender = asyncio.create_task(self._send_audio_loop(websocket))
                        receiver = asyncio.create_task(self._receive_loop(websocket))
                        done, pending = await asyncio.wait(
                            {sender, receiver},
                            return_when=asyncio.FIRST_EXCEPTION,
                        )
                        for task in pending:
                            task.cancel()
                        for task in done:
                            exc = task.exception()
                            if exc is not None:
                                raise exc
                except Exception as exc:
                    import websockets.exceptions
                    if isinstance(exc, (websockets.exceptions.ConnectionClosedOK,
                                        websockets.exceptions.ConnectionClosedError)):
                        if not self._running:
                            break
                        print(f"[elevenlabs] connection closed ({exc}), reconnecting in {reconnect_delay:.1f}s")
                        await asyncio.sleep(reconnect_delay)
                        reconnect_delay = min(reconnect_delay * 2, 30.0)
                        self._sent_previous_text = False
                        continue
                    raise
        finally:
            self.microphone.stop()
            self._running = False

    def stop(self) -> None:
        """Stop the realtime streaming loop."""
        self._running = False

    async def _send_audio_loop(self, websocket) -> None:
        try:
            while self._running:
                chunk = await self.microphone.read_chunk(timeout=0.5)
                if chunk is None:
                    continue
                await websocket.send(json.dumps(self._build_audio_message(chunk)))
        except Exception as exc:
            import websockets.exceptions
            if isinstance(exc, websockets.exceptions.ConnectionClosedOK):
                return  # server closed gracefully
            raise

    async def _receive_loop(self, websocket) -> None:
        try:
            while self._running:
                raw_message = await websocket.recv()
                payload = json.loads(raw_message)
                message_type = payload.get("message_type", "")

                if message_type == "session_started":
                    continue

                if message_type == "partial_transcript":
                    await self._handle_partial(payload.get("text", ""))
                    continue

                if message_type in {"committed_transcript", "committed_transcript_with_timestamps"}:
                    await self._handle_final(payload.get("text", ""))
                    continue

                if "error" in message_type or message_type.endswith("_error"):
                    raise RuntimeError(payload.get("message") or payload.get("error") or str(payload))
        except Exception as exc:
            import websockets.exceptions
            if isinstance(exc, websockets.exceptions.ConnectionClosedOK):
                return  # server closed gracefully
            raise

    def _build_audio_message(self, chunk: AudioChunk) -> dict:
        message = {
            "message_type": "input_audio_chunk",
            "audio_base_64": base64.b64encode(chunk.data).decode("ascii"),
            "sample_rate": chunk.sample_rate,
        }
        if not self._sent_previous_text and self.config.previous_text:
            message["previous_text"] = self.config.previous_text[:50]
            self._sent_previous_text = True
        return message

    async def _handle_partial(self, text: str) -> None:
        normalized = text.strip()
        if not normalized:
            return
        event = TranscriptEvent(
            type="partial",
            transcript_id=self._current_transcript_id,
            text=normalized,
            timestamp=time.time(),
            source="elevenlabs",
        )
        if self.on_event is not None:
            await self.on_event(event)

    async def _handle_final(self, text: str) -> None:
        normalized = text.strip()
        if not normalized:
            return
        event = TranscriptEvent(
            type="final",
            transcript_id=self._current_transcript_id,
            text=normalized,
            timestamp=time.time(),
            source="elevenlabs",
        )
        if self.on_event is not None:
            await self.on_event(event)
        await dispatch_transcript(event, self.agent_queue)
        self._current_transcript_id = self._next_transcript_id()

    def _next_transcript_id(self) -> str:
        return "tx_{:06d}".format(next(self._utterance_counter))
