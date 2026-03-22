"""Application entry point placeholder."""

import asyncio
import itertools
import os
import queue
import sys
import threading
import time
from typing import Any, Dict

from src.agent.command_text import canonicalize_command_text
from src.agent.controller import AgentController
from src.agent.loop import run_agent_loop
from src.shared.events import AgentCommand, TranscriptEvent, UIEvent
from src.shared.speech_output import should_suppress_transcripts
from src.transcription.backend import FasterWhisperBackend, MockTranscriptionBackend
from src.transcription.elevenlabs_realtime import (
    ElevenLabsRealtimeConfig,
    ElevenLabsRealtimeTranscriptionService,
)
from src.transcription.dispatcher import dispatch_transcript
from src.transcription.mic_capture import SoundDeviceMicrophone
from src.transcription.segmenter import SegmenterConfig, UtteranceSegmenter
from src.transcription.service import TranscriptionService


def should_prewarm_browser_use() -> bool:
    """Return whether the app should warm the browser-use server on startup."""
    if os.getenv("BROWSER_USE_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        return False
    try:
        from src.agent.browser_use_backend import browser_use_available
    except Exception:
        return False
    return browser_use_available()


async def prewarm_browser_use() -> None:
    """Warm the browser-use server outside the first user command."""
    try:
        from src.agent.browser_use_backend import prewarm_browser_use_server
    except Exception as exc:
        print(f"[prewarm] browser-use unavailable: {exc}")
        return

    started_at = time.perf_counter()
    try:
        await prewarm_browser_use_server()
        print("[timing] browser-use prewarm took {:.1f}ms".format((time.perf_counter() - started_at) * 1000.0))
    except Exception as exc:
        print(f"[prewarm] browser-use failed: {exc}")


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
    if should_suppress_transcripts(event.source):
        return
    normalized_text = canonicalize_command_text(event.text)
    print("[{}] {}".format(event.type, normalized_text))
    publish_ui_event(
        event_queue,
        "transcript",
        {
            "kind": event.type,
            "text": normalized_text,
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


def build_elevenlabs_service(
    agent_queue: "asyncio.Queue[AgentCommand]",
    on_event,
) -> ElevenLabsRealtimeTranscriptionService:
    """Construct the ElevenLabs realtime transcription service from environment settings."""
    return ElevenLabsRealtimeTranscriptionService(
        microphone=SoundDeviceMicrophone(
            sample_rate=int(os.getenv("MIC_SAMPLE_RATE", "16000")),
            channels=int(os.getenv("MIC_CHANNELS", "1")),
            chunk_ms=int(os.getenv("MIC_CHUNK_MS", "250")),
        ),
        agent_queue=agent_queue,
        config=ElevenLabsRealtimeConfig(
            model_id=os.getenv("ELEVENLABS_MODEL_ID", "scribe_v2_realtime"),
            language_code=os.getenv("ELEVENLABS_LANGUAGE_CODE", "en"),
            include_timestamps=os.getenv("ELEVENLABS_INCLUDE_TIMESTAMPS", "0") == "1",
            include_language_detection=os.getenv("ELEVENLABS_INCLUDE_LANGUAGE_DETECTION", "0") == "1",
            commit_strategy=os.getenv("ELEVENLABS_COMMIT_STRATEGY", "vad"),
            vad_silence_threshold_secs=float(os.getenv("ELEVENLABS_VAD_SILENCE_THRESHOLD_SECS", "0.7")),
            vad_threshold=float(os.getenv("ELEVENLABS_VAD_THRESHOLD", "0.45")),
            min_speech_duration_ms=int(os.getenv("ELEVENLABS_MIN_SPEECH_DURATION_MS", "120")),
            min_silence_duration_ms=int(os.getenv("ELEVENLABS_MIN_SILENCE_DURATION_MS", "160")),
            previous_text=os.getenv(
                "ELEVENLABS_PREVIOUS_TEXT",
                "Voice commands for Mac control and YouTube.",
            ),
        ),
        on_event=on_event,
    )


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
    fake_transcript = os.getenv("FAKE_TRANSCRIPT_TEXT", "").strip()
    transcription_backend_name = os.getenv("TRANSCRIPTION_BACKEND", "mock").strip().lower()
    input_mode = os.getenv("DEV_INPUT_MODE", "").strip().lower()
    wispr_mode = input_mode == "wispr"
    type_mode = input_mode == "type"
    if wispr_mode and overlay_class is None:
        print("[ui] Wispr mode requires the overlay; falling back to terminal type mode")
        wispr_mode = False
        type_mode = True
    text_input_mode = type_mode or wispr_mode
    if text_input_mode and fake_transcript:
        print("[main] ignoring FAKE_TRANSCRIPT_TEXT because interactive input mode is active")
        fake_transcript = ""
    active_mode = "wispr" if wispr_mode else ("type" if type_mode else ("mock" if fake_transcript else "microphone"))
    print(f"[main] startup mode={active_mode}")
    transcript_counter = itertools.count(1)

    async def submit_command_text(text: str, transcript_id: str) -> None:
        normalized = canonicalize_command_text(text)
        if not normalized:
            return
        source = "wispr" if wispr_mode else ("typed" if type_mode else ("fake_transcript" if fake_transcript else "microphone"))
        event = TranscriptEvent(
            type="final",
            transcript_id=transcript_id,
            text=normalized,
            timestamp=0.0,
            source=source,
        )
        await log_event(event, ui_queue)
        await dispatch_transcript(
            event,
            shared["agent_queue"],
            metadata={"source": source},
        )

    def queue_overlay_text(text: str) -> None:
        loop = shared.get("loop")
        if loop is None:
            return
        transcript_id = ("wispr" if wispr_mode else "typed") + "_tx_{:06d}".format(next(transcript_counter))

        async def submit() -> None:
            await submit_command_text(text, transcript_id)

        loop.call_soon_threadsafe(lambda: asyncio.create_task(submit()))

    def start_backend() -> None:
        async def backend_runner() -> None:
            agent_queue: "asyncio.Queue[AgentCommand]" = asyncio.Queue()
            controller = AgentController()

            shared["agent_queue"] = agent_queue
            shared["controller"] = controller

            loop_ready.set()

            consumer_task = asyncio.create_task(
                run_agent_loop(
                    agent_queue,
                    controller=controller,
                    on_status=lambda state, detail: handle_agent_status(state, detail, ui_queue),
                )
            )

            if should_prewarm_browser_use() and not text_input_mode and not fake_transcript:
                publish_ui_event(
                    ui_queue,
                    "agent_status",
                    {
                        "state": "warming",
                        "detail": "Preparing browser",
                    },
                )
                await prewarm_browser_use()

            publish_ui_event(
                ui_queue,
                "agent_status",
                {
                    "state": "listening",
                    "detail": (
                        "Wispr dictation ready"
                        if wispr_mode
                        else ("Type mode" if text_input_mode else ("Typed test mode" if fake_transcript else "Mic live"))
                    ),
                },
            )

            service = None
            typed_task = None
            if fake_transcript:
                await submit_command_text(fake_transcript, "fake_tx_000001")
            elif type_mode:
                event_loop = asyncio.get_event_loop()

                def stdin_reader() -> None:
                    counter = 1
                    while True:
                        try:
                            sys.stdout.write("type> ")
                            sys.stdout.flush()
                            line = sys.stdin.readline()
                        except (EOFError, OSError):
                            break
                        if not line:
                            break
                        line = line.strip()
                        if not line:
                            continue
                        tx_id = "typed_tx_{:06d}".format(counter)
                        counter += 1
                        event_loop.call_soon_threadsafe(
                            lambda t=line, i=tx_id: asyncio.create_task(submit_command_text(t, i))
                        )

                stdin_thread = threading.Thread(target=stdin_reader, daemon=True)
                stdin_thread.start()
            elif wispr_mode:
                print("[main] Wispr mode active; transcription service disabled")
            else:
                if transcription_backend_name == "elevenlabs":
                    service = build_elevenlabs_service(
                        agent_queue=agent_queue,
                        on_event=lambda event: log_event(event, ui_queue),
                    )
                else:
                    service = TranscriptionService(
                        microphone=SoundDeviceMicrophone(),
                        backend=build_transcription_backend(),
                        segmenter=UtteranceSegmenter(SegmenterConfig()),
                        agent_queue=agent_queue,
                        on_event=lambda event: log_event(event, ui_queue),
                    )
                shared["service"] = service

            try:
                if service is not None:
                    await service.start()
                else:
                    while True:
                        await asyncio.sleep(0.2)
            finally:
                if service is not None:
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

    overlay = overlay_class(
        event_queue=ui_queue,
        on_stop=stop_llm,
        on_quit=quit_app,
        on_submit_text=queue_overlay_text if wispr_mode else None,
        input_mode="wispr" if wispr_mode else "",
    )
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
