# produhacks-26

Voice-driven Mac control prototype.

## Project Layout

This repo is split so the team can work on speech and tool execution independently:

- `src/transcription/`
  Always-on microphone capture, transcription, utterance segmentation, and command handoff.
- `src/agent/`
  Command interpretation and planning over tool calls.
- `src/tool_runtime/`
  Mac control primitives such as screenshot, click, scroll, typing, and keypress execution.
- `src/shared/`
  Shared event models and common types.
- `docs/`
  Architecture notes and API docs.

## Near-Term Goal

Keep the interfaces between these areas stable:

- transcription emits finalized transcript events
- agent consumes transcript events and emits tool calls
- tool runtime executes tool calls and returns results

## Local Transcription

The transcription layer now includes:

- `src/transcription/mic_capture.py`
  Continuous microphone capture with `sounddevice`
- `src/transcription/segmenter.py`
  Silence-based utterance finalization
- `src/transcription/backend.py`
  Local Whisper-style backend interface with `faster-whisper`
- `src/transcription/service.py`
  Always-on loop that emits partial and final transcript events and forwards final commands to the agent queue

## Running The Skeleton

Install dependencies:

```bash
pip install -r requirements.txt
```

Quick smoke test with the mock backend:

```bash
python3 -m src.main
```

Use the real local Whisper backend:

```bash
TRANSCRIPTION_BACKEND=faster-whisper WHISPER_MODEL_SIZE=base python3 -m src.main
```

The app entry point logs transcript events and sends finalized commands into a simple agent loop.

## How To Test

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Smoke test the wiring

This proves the app boots and the event plumbing works:

```bash
python3 -m py_compile src/main.py src/agent/loop.py src/transcription/*.py src/shared/events.py
```

### 3. Run with the real local backend

```bash
TRANSCRIPTION_BACKEND=faster-whisper WHISPER_MODEL_SIZE=base python3 -m src.main
```

Then:

- allow microphone permission if macOS prompts
- say a short command such as `scroll down`
- pause for about a second
- look for `[final] ...` in the terminal
- look for `[agent] transcript=...` and `[plan] ...` immediately after

### 4. If you want a lightweight backend first

You can run:

```bash
python3 -m src.main
```

That uses the mock backend. It is only useful for checking startup and queue wiring, not transcription quality.
