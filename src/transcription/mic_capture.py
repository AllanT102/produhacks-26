"""Microphone capture for streaming transcription."""

import asyncio
import queue
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class AudioChunk:
    """A PCM audio chunk captured from the microphone."""

    data: bytes
    sample_rate: int
    channels: int
    sample_width: int
    timestamp: float

    @property
    def duration_ms(self) -> float:
        """Return the chunk duration in milliseconds."""
        frame_width = self.channels * self.sample_width
        if frame_width == 0 or self.sample_rate == 0:
            return 0.0
        frames = len(self.data) / frame_width
        return (frames / self.sample_rate) * 1000.0


class SoundDeviceMicrophone:
    """Continuously capture mono 16-bit PCM audio from the default microphone."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_ms: int = 250,
        queue_size: int = 32,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_ms = chunk_ms
        self.sample_width = 2
        self.frames_per_chunk = int(sample_rate * (chunk_ms / 1000.0))
        self._queue = queue.Queue(maxsize=queue_size)
        self._stream = None
        self._running = False

    def start(self) -> None:
        """Start microphone capture."""
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "sounddevice is required for microphone capture. Install requirements.txt first."
            ) from exc

        if self._running:
            return

        def callback(indata, frames, _time, status) -> None:
            if status:
                # Keep going. The service can surface dropped chunks later if needed.
                pass
            payload = AudioChunk(
                data=bytes(indata),
                sample_rate=self.sample_rate,
                channels=self.channels,
                sample_width=self.sample_width,
                timestamp=time.time(),
            )
            try:
                self._queue.put_nowait(payload)
            except queue.Full:
                # Drop the oldest chunk to preserve low-latency behavior.
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
                self._queue.put_nowait(payload)

        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=self.frames_per_chunk,
            callback=callback,
        )
        self._stream.start()
        self._running = True

    def stop(self) -> None:
        """Stop microphone capture."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._running = False

    async def read_chunk(self, timeout: Optional[float] = None) -> Optional[AudioChunk]:
        """Return the next available chunk or None if a timeout expires."""
        if not self._running:
            raise RuntimeError("Microphone capture is not running.")

        def _get() -> Optional[AudioChunk]:
            try:
                return self._queue.get(timeout=timeout)
            except queue.Empty:
                return None

        return await asyncio.to_thread(_get)
