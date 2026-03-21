"""Utterance segmentation for always-on speech control."""

import audioop
from dataclasses import dataclass, field
from typing import List, Optional

from src.transcription.mic_capture import AudioChunk


@dataclass
class SegmenterConfig:
    """Tune utterance boundaries for command-style speech."""

    silence_threshold: int = 450
    silence_ms_to_finalize: int = 700
    min_speech_ms: int = 250
    max_buffer_ms: int = 12000


@dataclass
class Segment:
    """A finalized utterance payload."""

    transcript_id: str
    audio: bytes
    sample_rate: int
    channels: int
    sample_width: int
    started_at: float
    ended_at: float


@dataclass
class SegmenterState:
    """Current segmentation state."""

    chunks: List[AudioChunk] = field(default_factory=list)
    speech_ms: float = 0.0
    trailing_silence_ms: float = 0.0
    started_at: Optional[float] = None
    utterance_index: int = 0


class UtteranceSegmenter:
    """Build utterances from continuous microphone chunks."""

    def __init__(self, config: Optional[SegmenterConfig] = None) -> None:
        self.config = config or SegmenterConfig()
        self.state = SegmenterState()

    def add_chunk(self, chunk: AudioChunk) -> Optional[Segment]:
        """Consume a chunk and return a finalized segment if one closes."""
        rms = audioop.rms(chunk.data, chunk.sample_width)
        is_speech = rms >= self.config.silence_threshold

        if self.state.started_at is None:
            self.state.started_at = chunk.timestamp

        self.state.chunks.append(chunk)

        if is_speech:
            self.state.speech_ms += chunk.duration_ms
            self.state.trailing_silence_ms = 0.0
        else:
            self.state.trailing_silence_ms += chunk.duration_ms

        buffered_ms = sum(item.duration_ms for item in self.state.chunks)
        if buffered_ms >= self.config.max_buffer_ms and self.state.speech_ms >= self.config.min_speech_ms:
            return self._finalize(chunk.timestamp)

        if (
            self.state.speech_ms >= self.config.min_speech_ms
            and self.state.trailing_silence_ms >= self.config.silence_ms_to_finalize
        ):
            return self._finalize(chunk.timestamp)

        if self.state.speech_ms == 0 and self.state.trailing_silence_ms >= self.config.silence_ms_to_finalize:
            self.reset()

        return None

    def get_buffered_audio(self) -> Optional[bytes]:
        """Return the current buffered utterance audio, if any."""
        if not self.state.chunks:
            return None
        return b"".join(chunk.data for chunk in self.state.chunks)

    def has_minimum_speech(self) -> bool:
        """Return whether the current buffer likely contains real speech."""
        return self.state.speech_ms >= self.config.min_speech_ms

    def current_speech_ms(self) -> float:
        """Return buffered speech duration in milliseconds."""
        return self.state.speech_ms

    def current_transcript_id(self) -> str:
        """Return a stable transcript id for the current utterance buffer."""
        return "tx_{:06d}".format(self.state.utterance_index + 1)

    def reset(self) -> None:
        """Clear segmentation state."""
        self.state = SegmenterState(utterance_index=self.state.utterance_index)

    def _finalize(self, ended_at: float) -> Segment:
        first = self.state.chunks[0]
        segment = Segment(
            transcript_id=self.current_transcript_id(),
            audio=b"".join(chunk.data for chunk in self.state.chunks),
            sample_rate=first.sample_rate,
            channels=first.channels,
            sample_width=first.sample_width,
            started_at=self.state.started_at or first.timestamp,
            ended_at=ended_at,
        )
        next_index = self.state.utterance_index + 1
        self.state = SegmenterState(utterance_index=next_index)
        return segment
