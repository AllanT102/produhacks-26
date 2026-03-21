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

## Dev Shortcuts

You can use either `make` or the shell scripts in `scripts/`.

### Setup

```bash
make setup
```

or

```bash
./scripts/setup.sh
```

### Syntax check

```bash
make check
```

or

```bash
./scripts/check.sh
```

### Run with mock backend

```bash
make run-mock
```

or

```bash
./scripts/run_mock.sh
```

### Run with local Whisper backend

```bash
make run-whisper
```

or

```bash
./scripts/run_whisper.sh
```

To use a different model size:

```bash
WHISPER_MODEL_SIZE=small make run-whisper
```

The app entry point logs transcript events and sends finalized commands into a simple agent loop.

## How To Test

### 1. Install dependencies

```bash
make setup
```

### 2. Smoke test the wiring

This proves the app boots and the event plumbing works:

```bash
make check
```

### 3. Run with the real local backend

```bash
make run-whisper
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
make run-mock
```

That uses the mock backend. It is only useful for checking startup and queue wiring, not transcription quality.
