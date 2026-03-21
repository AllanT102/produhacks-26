"""Continuous local transcription service."""

import asyncio
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from src.shared.events import TranscriptEvent
from src.transcription.backend import LocalTranscriptionBackend
from src.transcription.dispatcher import dispatch_transcript
from src.transcription.mic_capture import SoundDeviceMicrophone
from src.transcription.segmenter import Segment, UtteranceSegmenter

TranscriptCallback = Callable[[TranscriptEvent], Awaitable[None]]


@dataclass
class TranscriptionServiceConfig:
    """Control the cadence of partial and final transcript updates."""

    partial_interval_ms: int = 900
    min_transcript_characters: int = 2


class TranscriptionService:
    """Run an always-on local transcription loop and feed the agent queue."""

    def __init__(
        self,
        microphone: SoundDeviceMicrophone,
        backend: LocalTranscriptionBackend,
        segmenter: UtteranceSegmenter,
        agent_queue: "asyncio.Queue",
        config: Optional[TranscriptionServiceConfig] = None,
        on_event: Optional[TranscriptCallback] = None,
    ) -> None:
        self.microphone = microphone
        self.backend = backend
        self.segmenter = segmenter
        self.agent_queue = agent_queue
        self.config = config or TranscriptionServiceConfig()
        self.on_event = on_event
        self._running = False
        self._last_partial_at = 0.0

    async def start(self) -> None:
        """Start microphone capture and process audio forever."""
        self.microphone.start()
        self._running = True

        try:
            while self._running:
                chunk = await self.microphone.read_chunk(timeout=0.5)
                if chunk is None:
                    continue

                segment = self.segmenter.add_chunk(chunk)
                await self._maybe_emit_partial()

                if segment is not None:
                    await self._handle_final_segment(segment)
        finally:
            self.microphone.stop()

    def stop(self) -> None:
        """Stop the transcription loop."""
        self._running = False

    async def _maybe_emit_partial(self) -> None:
        buffered_audio = self.segmenter.get_buffered_audio()
        if buffered_audio is None:
            return
        if not self.segmenter.has_minimum_speech():
            return

        now = time.time()
        interval_seconds = self.config.partial_interval_ms / 1000.0
        if now - self._last_partial_at < interval_seconds:
            return

        transcript_text = await asyncio.to_thread(
            self.backend.transcribe,
            buffered_audio,
            self.microphone.sample_rate,
            self.microphone.channels,
            self.microphone.sample_width,
        )
        if len(transcript_text.strip()) < self.config.min_transcript_characters:
            return

        event = TranscriptEvent(
            type="partial",
            transcript_id=self.segmenter.current_transcript_id(),
            text=transcript_text.strip(),
            timestamp=now,
        )
        self._last_partial_at = now
        if self.on_event is not None:
            await self.on_event(event)

    async def _handle_final_segment(self, segment: Segment) -> None:
        text = await asyncio.to_thread(
            self.backend.transcribe,
            segment.audio,
            segment.sample_rate,
            segment.channels,
            segment.sample_width,
        )
        text = text.strip()
        if len(text) < self.config.min_transcript_characters:
            return

        event = TranscriptEvent(
            type="final",
            transcript_id=segment.transcript_id,
            text=text,
            timestamp=segment.ended_at,
        )
        if self.on_event is not None:
            await self.on_event(event)
        await dispatch_transcript(event, self.agent_queue)
