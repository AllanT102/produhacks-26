#!/usr/bin/env python3
"""Debug microphone capture and local transcription without the full app loop."""

import argparse
import asyncio
import audioop
import os
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.transcription.backend import FasterWhisperBackend
from src.transcription.mic_capture import SoundDeviceMicrophone
from src.transcription.segmenter import Segment, SegmenterConfig, UtteranceSegmenter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect live microphone chunks, speech detection, and optional faster-whisper output.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=0.0,
        help="Run for a fixed number of seconds. Use 0 to run until Ctrl-C.",
    )
    parser.add_argument(
        "--meter-only",
        action="store_true",
        help="Only show microphone and speech-detection stats. Skip faster-whisper transcription.",
    )
    parser.add_argument(
        "--partial-interval-ms",
        type=int,
        default=900,
        help="How often to emit partial transcriptions while speech is buffered.",
    )
    return parser


async def transcribe_segment(
    backend: FasterWhisperBackend,
    segment: Segment,
) -> str:
    return await asyncio.to_thread(
        backend.transcribe,
        segment.audio,
        segment.sample_rate,
        segment.channels,
        segment.sample_width,
    )


async def transcribe_buffer(
    backend: FasterWhisperBackend,
    audio: bytes,
    microphone: SoundDeviceMicrophone,
) -> str:
    return await asyncio.to_thread(
        backend.transcribe,
        audio,
        microphone.sample_rate,
        microphone.channels,
        microphone.sample_width,
    )


async def run() -> None:
    args = build_parser().parse_args()
    microphone = SoundDeviceMicrophone()
    segmenter = UtteranceSegmenter(SegmenterConfig())
    backend: Optional[FasterWhisperBackend] = None

    if not args.meter_only:
        print(
            "[debug] loading faster-whisper model={} device={} compute_type={}".format(
                os.getenv("WHISPER_MODEL_SIZE", "base"),
                os.getenv("WHISPER_DEVICE", "auto"),
                os.getenv("WHISPER_COMPUTE_TYPE", "default"),
            )
        )
        backend = FasterWhisperBackend(
            model_size=os.getenv("WHISPER_MODEL_SIZE", "base"),
            device=os.getenv("WHISPER_DEVICE", "auto"),
            compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "default"),
            language=os.getenv("WHISPER_LANGUAGE", "en"),
        )

    started_at = time.time()
    last_meter_at = 0.0
    last_partial_at = 0.0
    partial_interval_s = max(args.partial_interval_ms, 100) / 1000.0
    chunk_count = 0
    max_rms = 0

    microphone.start()
    print(
        "[debug] microphone started sample_rate={} chunk_ms={} threshold={}".format(
            microphone.sample_rate,
            microphone.chunk_ms,
            segmenter.config.silence_threshold,
        )
    )
    print("[debug] speak now; Ctrl-C to stop")

    try:
        while True:
            if args.seconds > 0 and (time.time() - started_at) >= args.seconds:
                break

            chunk = await microphone.read_chunk(timeout=0.5)
            if chunk is None:
                print("[meter] no chunk for 500ms")
                continue

            chunk_count += 1
            rms = audioop.rms(chunk.data, chunk.sample_width)
            max_rms = max(max_rms, rms)
            segment = segmenter.add_chunk(chunk)
            now = time.time()
            is_speech = rms >= segmenter.config.silence_threshold

            if now - last_meter_at >= 0.45:
                print(
                    "[meter] rms={} speech={} speech_ms={:.0f} trailing_silence_ms={:.0f} chunks={}".format(
                        rms,
                        "yes" if is_speech else "no",
                        segmenter.current_speech_ms(),
                        segmenter.state.trailing_silence_ms,
                        chunk_count,
                    )
                )
                last_meter_at = now

            if backend is not None:
                buffered_audio = segmenter.get_buffered_audio()
                if (
                    buffered_audio is not None
                    and segmenter.has_minimum_speech()
                    and (now - last_partial_at) >= partial_interval_s
                ):
                    partial_text = (await transcribe_buffer(backend, buffered_audio, microphone)).strip()
                    if partial_text:
                        print("[partial] {}".format(partial_text))
                    last_partial_at = now

                if segment is not None:
                    final_text = (await transcribe_segment(backend, segment)).strip()
                    print("[final] {}".format(final_text or "<empty>"))
                    last_partial_at = 0.0
            elif segment is not None:
                print(
                    "[segment] finalized transcript_id={} duration_ms={:.0f}".format(
                        segment.transcript_id,
                        (segment.ended_at - segment.started_at) * 1000.0,
                    )
                )
    except KeyboardInterrupt:
        print("\n[debug] stopped by user")
    finally:
        microphone.stop()
        print("[debug] microphone stopped chunks={} max_rms={}".format(chunk_count, max_rms))


if __name__ == "__main__":
    asyncio.run(run())
