#!/usr/bin/env bash
set -euo pipefail

source .venv/bin/activate
export TRANSCRIPTION_BACKEND=faster-whisper
export WHISPER_MODEL_SIZE="${WHISPER_MODEL_SIZE:-base}"
python3 -m src.main
