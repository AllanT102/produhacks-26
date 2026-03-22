PYTHON ?= python3
VENV := .venv
ACTIVATE := . $(VENV)/bin/activate

.PHONY: setup check run-mock run-whisper run-type run-wispr run-experiment

setup:
	$(PYTHON) -m venv $(VENV)
	$(ACTIVATE) && pip install --upgrade pip
	$(ACTIVATE) && pip install -r requirements.txt

check:
	$(ACTIVATE) && python3 -m py_compile scripts/browser_compare.py scripts/browser_use_direct.py scripts/browser_use_server.py src/main.py src/agent/browser_use_backend.py src/agent/controller.py src/agent/experiments.py src/agent/loop.py src/agent/mock_executor.py src/agent/planner.py src/shared/events.py src/ui/overlay.py src/transcription/backend.py src/transcription/dispatcher.py src/transcription/mic_capture.py src/transcription/segmenter.py src/transcription/service.py src/tool_runtime/runtime.py src/tool_runtime/schemas.py src/tool_runtime/tools/__init__.py src/tool_runtime/tools/app.py src/tool_runtime/tools/browser.py src/tool_runtime/tools/brightness.py src/tool_runtime/tools/click.py src/tool_runtime/tools/screenshot.py src/tool_runtime/tools/scroll.py src/tool_runtime/tools/keyboard.py src/tool_runtime/tools/mouse.py src/tool_runtime/tools/targets.py src/tool_runtime/tools/volume.py

run-mock:
	$(ACTIVATE) && BROWSER_USE_ENABLED=$${BROWSER_USE_ENABLED:-1} FAKE_TRANSCRIPT_TEXT="$${FAKE_TRANSCRIPT_TEXT:-$${MOCK_TRANSCRIPT_TEXT:-test command}}" python3 -m src.main

run-whisper:
	$(ACTIVATE) && BROWSER_USE_ENABLED=$${BROWSER_USE_ENABLED:-1} TRANSCRIPTION_BACKEND=faster-whisper WHISPER_MODEL_SIZE=$${WHISPER_MODEL_SIZE:-base} python3 -m src.main

run-type:
	$(ACTIVATE) && unset FAKE_TRANSCRIPT_TEXT MOCK_TRANSCRIPT_TEXT && BROWSER_USE_ENABLED=$${BROWSER_USE_ENABLED:-1} DEV_INPUT_MODE=type python3 -m src.main

run-wispr:
	$(ACTIVATE) && unset FAKE_TRANSCRIPT_TEXT MOCK_TRANSCRIPT_TEXT && BROWSER_USE_ENABLED=$${BROWSER_USE_ENABLED:-1} DEV_INPUT_MODE=wispr python3 -m src.main

run-experiment:
	$(ACTIVATE) && python3 -m src.agent.experiments --scenario $${SCENARIO:-youtube_search} --goal "$${GOAL:-search for lo-fi beats}"
