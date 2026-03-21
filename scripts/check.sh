#!/usr/bin/env bash
set -euo pipefail

source .venv/bin/activate
python3 -m py_compile \
  src/main.py \
  src/agent/controller.py \
  src/agent/experiments.py \
  src/agent/loop.py \
  src/agent/mock_executor.py \
  src/agent/planner.py \
  src/shared/events.py \
  src/ui/overlay.py \
  src/transcription/backend.py \
  src/transcription/dispatcher.py \
  src/transcription/mic_capture.py \
  src/transcription/segmenter.py \
  src/transcription/service.py \
  src/tool_runtime/runtime.py \
  src/tool_runtime/schemas.py \
  src/tool_runtime/tools/__init__.py \
  src/tool_runtime/tools/app.py \
  src/tool_runtime/tools/brightness.py \
  src/tool_runtime/tools/click.py \
  src/tool_runtime/tools/targets.py \
  src/tool_runtime/tools/screenshot.py \
  src/tool_runtime/tools/scroll.py \
  src/tool_runtime/tools/keyboard.py \
  src/tool_runtime/tools/mouse.py \
  src/tool_runtime/tools/volume.py

echo "Syntax check passed."
