#!/usr/bin/env bash
set -euo pipefail

source .venv/bin/activate
python3 -m py_compile \
  src/main.py \
  src/agent/loop.py \
  src/agent/planner.py \
  src/shared/events.py \
  src/transcription/backend.py \
  src/transcription/dispatcher.py \
  src/transcription/mic_capture.py \
  src/transcription/segmenter.py \
  src/transcription/service.py \
  src/tool_runtime/runtime.py

echo "Syntax check passed."
