PYTHON ?= python3
VENV := .venv
ACTIVATE := . $(VENV)/bin/activate

.PHONY: setup check run-mock run-whisper

setup:
	$(PYTHON) -m venv $(VENV)
	$(ACTIVATE) && pip install --upgrade pip
	$(ACTIVATE) && pip install -r requirements.txt

check:
	$(ACTIVATE) && python3 -m py_compile src/main.py src/agent/loop.py src/agent/planner.py src/shared/events.py src/transcription/backend.py src/transcription/dispatcher.py src/transcription/mic_capture.py src/transcription/segmenter.py src/transcription/service.py src/tool_runtime/runtime.py src/tool_runtime/schemas.py src/tool_runtime/tools/__init__.py src/tool_runtime/tools/click.py src/tool_runtime/tools/screenshot.py src/tool_runtime/tools/scroll.py src/tool_runtime/tools/keyboard.py src/tool_runtime/tools/mouse.py

run-mock:
	$(ACTIVATE) && python3 -m src.main

run-whisper:
	$(ACTIVATE) && TRANSCRIPTION_BACKEND=faster-whisper WHISPER_MODEL_SIZE=$${WHISPER_MODEL_SIZE:-base} python3 -m src.main
