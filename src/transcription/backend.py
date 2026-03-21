"""Local Whisper-style transcription backends."""

import io
import wave
from abc import ABC, abstractmethod
from array import array
from typing import Optional


class LocalTranscriptionBackend(ABC):
    """Base contract for local transcription backends."""

    @abstractmethod
    def transcribe(self, audio: bytes, sample_rate: int, channels: int, sample_width: int) -> str:
        """Return a transcription for a PCM utterance."""


class FasterWhisperBackend(LocalTranscriptionBackend):
    """Transcribe utterances with a local faster-whisper model."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "default",
        language: Optional[str] = "en",
        beam_size: int = 1,
    ) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is required for local transcription. Install requirements.txt first."
            ) from exc

        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self.language = language
        self.beam_size = beam_size

    def transcribe(self, audio: bytes, sample_rate: int, channels: int, sample_width: int) -> str:
        """Run transcription against a WAV-encoded in-memory buffer."""
        wav_buffer = _pcm_to_wav_bytes(
            audio=audio,
            sample_rate=sample_rate,
            channels=channels,
            sample_width=sample_width,
        )
        segments, _info = self._model.transcribe(
            wav_buffer,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()


class MockTranscriptionBackend(LocalTranscriptionBackend):
    """A test backend that returns a fixed string."""

    def __init__(self, text: str = "test command") -> None:
        self.text = text

    def transcribe(self, audio: bytes, sample_rate: int, channels: int, sample_width: int) -> str:
        del audio, sample_rate, channels, sample_width
        return self.text


def _pcm_to_wav_bytes(audio: bytes, sample_rate: int, channels: int, sample_width: int):
    """Convert PCM bytes to a WAV-like file object acceptable to transcription backends."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio)
    buffer.seek(0)
    return buffer


def pcm16le_to_float32(audio: bytes):
    """Convert little-endian PCM16 bytes to normalized float32 samples."""
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("numpy is required to convert PCM audio to float32 arrays.") from exc

    samples = array("h")
    samples.frombytes(audio)
    if samples.itemsize != 2:
        raise ValueError("Expected 16-bit PCM samples.")
    return np.array(samples, dtype=np.float32) / 32768.0
