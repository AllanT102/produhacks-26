PYTHON ?= python3
VENV := .venv
ACTIVATE := . $(VENV)/bin/activate

.PHONY: setup check run-mock run-whisper run-experiment

setup:
	$(PYTHON) -m venv $(VENV)
	$(ACTIVATE) && pip install --upgrade pip
	$(ACTIVATE) && pip install -r requirements.txt
	$(ACTIVATE) && playwright install chrome

check:
	$(ACTIVATE) && python3 -m py_compile src/main.py src/agent/controller.py src/agent/experiments.py src/agent/loop.py src/agent/mock_executor.py src/agent/planner.py src/shared/events.py src/ui/overlay.py src/transcription/backend.py src/transcription/dispatcher.py src/transcription/mic_capture.py src/transcription/segmenter.py src/transcription/service.py src/tool_runtime/runtime.py src/tool_runtime/schemas.py src/tool_runtime/tools/__init__.py src/tool_runtime/tools/browser.py src/tool_runtime/tools/brightness.py src/tool_runtime/tools/click.py src/tool_runtime/tools/find_elements.py src/tool_runtime/tools/get_page_info.py src/tool_runtime/tools/key_press.py src/tool_runtime/tools/navigate.py src/tool_runtime/tools/screenshot.py src/tool_runtime/tools/scroll.py src/tool_runtime/tools/tab_ops.py src/tool_runtime/tools/type_text.py src/tool_runtime/tools/volume.py

run-mock:
	$(ACTIVATE) && python3 -m src.main

run-whisper:
	$(ACTIVATE) && TRANSCRIPTION_BACKEND=faster-whisper WHISPER_MODEL_SIZE=$${WHISPER_MODEL_SIZE:-base} python3 -m src.main

run-experiment:
	$(ACTIVATE) && python3 -m src.agent.experiments --scenario $${SCENARIO:-youtube_search} --goal "$${GOAL:-search for lo-fi beats}"
