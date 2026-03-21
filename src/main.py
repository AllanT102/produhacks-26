"""Application entry point placeholder."""

import asyncio
import os
import queue
import threading
from typing import Any, Dict

from src.agent.controller import AgentController
from src.agent.loop import run_agent_loop
from src.shared.events import AgentCommand, TranscriptEvent, UIEvent
from src.transcription.backend import FasterWhisperBackend, MockTranscriptionBackend
from src.transcription.mic_capture import SoundDeviceMicrophone
from src.transcription.segmenter import SegmenterConfig, UtteranceSegmenter
from src.transcription.service import TranscriptionService


def publish_ui_event(event_queue: "queue.Queue[UIEvent]", event_type: str, payload: dict) -> None:
    """Push a UI event without blocking the async runtime."""
    event_queue.put(UIEvent(type=event_type, payload=payload))


def clear_agent_queue(agent_queue: "asyncio.Queue[AgentCommand]") -> None:
    """Drop queued commands after a stop request."""
    while True:
        try:
            agent_queue.get_nowait()
            agent_queue.task_done()
        except asyncio.QueueEmpty:
            break


async def log_event(event: TranscriptEvent, event_queue: "queue.Queue[UIEvent]") -> None:
    """Print transcript events for local debugging and update the overlay."""
    print("[{}] {}".format(event.type, event.text))
    publish_ui_event(
        event_queue,
        "transcript",
        {
            "kind": event.type,
            "text": event.text,
        },
    )


async def handle_agent_status(
    state: str,
    detail: str,
    event_queue: "queue.Queue[UIEvent]",
) -> None:
    """Forward agent state changes to the overlay."""
    publish_ui_event(
        event_queue,
        "agent_status",
        {
            "state": state,
            "detail": detail,
        },
    )


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


def load_overlay():
    """Load the optional desktop overlay."""
    try:
        from src.ui.overlay import VoiceOverlay
    except Exception as exc:
        print("[ui] overlay disabled: {}".format(exc))
        return None
    return VoiceOverlay


def main() -> None:
    """Start the app runtime and lightweight overlay."""
    ui_queue: "queue.Queue[UIEvent]" = queue.Queue()
    loop_ready = threading.Event()
    shutdown_complete = threading.Event()
    shared: Dict[str, Any] = {}
    overlay_class = load_overlay()

    def start_backend() -> None:
        async def backend_runner() -> None:
            agent_queue: "asyncio.Queue[AgentCommand]" = asyncio.Queue()
            controller = AgentController()

            shared["agent_queue"] = agent_queue
            shared["controller"] = controller

            publish_ui_event(
                ui_queue,
                "agent_status",
                {
                    "state": "listening",
                    "detail": "Mic live",
                },
            )

            service = TranscriptionService(
                microphone=SoundDeviceMicrophone(),
                backend=build_transcription_backend(),
                segmenter=UtteranceSegmenter(SegmenterConfig()),
                agent_queue=agent_queue,
                on_event=lambda event: log_event(event, ui_queue),
            )
            shared["service"] = service
            loop_ready.set()

            consumer_task = asyncio.create_task(
                run_agent_loop(
                    agent_queue,
                    controller=controller,
                    on_status=lambda state, detail: handle_agent_status(state, detail, ui_queue),
                )
            )
            try:
                await service.start()
            finally:
                service.stop()
                consumer_task.cancel()
                try:
                    await consumer_task
                except asyncio.CancelledError:
                    pass
                shutdown_complete.set()

        shared["loop"] = asyncio.new_event_loop()
        asyncio.set_event_loop(shared["loop"])
        shared["loop"].run_until_complete(backend_runner())

    backend_thread = threading.Thread(target=start_backend, daemon=True)
    backend_thread.start()
    loop_ready.wait()

    def stop_llm() -> None:
        controller = shared["controller"]
        loop = shared["loop"]
        agent_queue = shared["agent_queue"]

        def stop_now() -> None:
            controller.request_stop()
            clear_agent_queue(agent_queue)

        publish_ui_event(
            ui_queue,
            "agent_status",
            {
                "state": "stopped",
                "detail": "Stopping...",
            },
        )
        loop.call_soon_threadsafe(stop_now)

    def quit_app() -> None:
        controller = shared["controller"]
        loop = shared["loop"]
        agent_queue = shared["agent_queue"]
        service = shared.get("service")

        def stop_everything() -> None:
            controller.request_stop()
            clear_agent_queue(agent_queue)
            if service is not None:
                service.stop()

        publish_ui_event(
            ui_queue,
            "agent_status",
            {
                "state": "stopped",
                "detail": "Quitting...",
            },
        )
        loop.call_soon_threadsafe(stop_everything)

    if overlay_class is None:
        print("[ui] running without desktop overlay")
        try:
            backend_thread.join()
        except KeyboardInterrupt:
            stop_llm()
            service = shared.get("service")
            loop = shared.get("loop")
            if service is not None and loop is not None:
                loop.call_soon_threadsafe(service.stop)
        return

    overlay = overlay_class(event_queue=ui_queue, on_stop=stop_llm, on_quit=quit_app)
    try:
        overlay.run()
    finally:
        service = shared.get("service")
        loop = shared.get("loop")
        if service is not None and loop is not None:
            loop.call_soon_threadsafe(service.stop)
        shutdown_complete.wait(timeout=1.5)


if __name__ == "__main__":
    main()
