"""Application entry point placeholder."""

import asyncio
import os

from src.agent.loop import run_agent_loop
from src.shared.events import AgentCommand, TranscriptEvent
from src.transcription.backend import FasterWhisperBackend, MockTranscriptionBackend
from src.transcription.mic_capture import SoundDeviceMicrophone
from src.transcription.segmenter import SegmenterConfig, UtteranceSegmenter
from src.transcription.service import TranscriptionService


async def log_event(event: TranscriptEvent) -> None:
    """Print transcript events for local debugging."""
    print("[{}] {}".format(event.type, event.text))


def build_transcription_backend():
    """Select a local transcription backend from environment settings."""
    backend_name = os.getenv("TRANSCRIPTION_BACKEND", "mock").strip().lower()
    if backend_name == "faster-whisper":
        return FasterWhisperBackend(
            model_size=os.getenv("WHISPER_MODEL_SIZE", "base"),
            device=os.getenv("WHISPER_DEVICE", "auto"),
            compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "default"),
            language=os.getenv("WHISPER_LANGUAGE", "en"),
        )

    mock_text = os.getenv("MOCK_TRANSCRIPT_TEXT", "test command")
    return MockTranscriptionBackend(text=mock_text)


async def run_app() -> None:
    """Wire the transcription loop to a placeholder agent queue."""
    agent_queue: "asyncio.Queue[AgentCommand]" = asyncio.Queue()

    service = TranscriptionService(
        microphone=SoundDeviceMicrophone(),
        backend=build_transcription_backend(),
        segmenter=UtteranceSegmenter(SegmenterConfig()),
        agent_queue=agent_queue,
        on_event=log_event,
    )

    consumer_task = asyncio.create_task(run_agent_loop(agent_queue))
    try:
        await service.start()
    except KeyboardInterrupt:
        service.stop()
    finally:
        service.stop()
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass


def main() -> None:
    """Start the app runtime."""
    asyncio.run(run_app())


if __name__ == "__main__":
    main()
