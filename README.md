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

## Overlay UI

The app now opens a small always-on-top desktop overlay that shows:

- whether the system is listening, thinking, ready, or stopped
- the latest transcript text
- a `Stop` button that cancels the current agent run

This gives you a visible "LLM is running" state similar to the lightweight control surface you described.
The overlay uses native macOS Cocoa bindings through PyObjC instead of Tk.

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
It also launches the desktop overlay automatically.
If `PyObjC` is not installed yet, the app falls back to headless mode and prints a warning.

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

If you want the overlay too, reinstall dependencies after pulling the latest changes:

```bash
pip install -r requirements.txt
```

Then:

- allow microphone permission if macOS prompts
- say a short command such as `scroll down`
- pause for about a second
- watch the overlay move from `Listening` to `Thinking`
- look for `[final] ...` in the terminal
- look for `[agent] transcript=...` and `[plan] ...` immediately after
- click `Stop` while it says `Thinking` to cancel the current agent run

### 4. If you want a lightweight backend first

You can run:

```bash
make run-mock
```

That uses the mock backend. It is only useful for checking startup and queue wiring, not transcription quality.

## Local Planner Tests

Use this when you want to test the LLM planner without touching the real desktop automation layer.

The experiment runner uses:

- the real planner in `src/agent/planner.py`
- the real Anthropic API
- a mocked tool executor in `src/agent/mock_executor.py`

This is the fastest way to test:

- prompt quality
- tool-call sequencing
- stop conditions
- planner behavior before the real Mac tools are ready

### Prerequisites

1. Install dependencies:

```bash
make setup
```

2. Set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY=your_key_here
```

3. Optional: run a syntax check first:

```bash
make check
```

### Quick Start

Run the default local planner experiment:

```bash
GOAL="search for lo-fi beats" SCENARIO=youtube_search make run-experiment
```

You can also run it directly:

```bash
python3 -m src.agent.experiments --scenario youtube_search --goal "search for lo-fi beats"
```

### Available Scenarios

- `youtube_search`
  Starts on a YouTube home page with a visible search box.
- `youtube_open_first`
  Starts on a YouTube search results page with a visible first result.

### Example Commands

Search flow:

```bash
GOAL="search for lo-fi beats" SCENARIO=youtube_search make run-experiment
```

Open first result flow:

```bash
GOAL="open the first result" SCENARIO=youtube_open_first make run-experiment
```

Custom iteration limit:

```bash
python3 -m src.agent.experiments \
  --scenario youtube_search \
  --goal "search for antique restoration videos" \
  --max-iterations 8
```

### What You Should See

The planner will print:

- the user goal
- each iteration number
- each tool call chosen by the model
- a final experiment summary
- the full mock tool history

Typical successful output will end with lines shaped like:

```text
[experiment] summary=...
[experiment] scenario=youtube_search
[experiment] tool_history=[...]
```

### Notes

- These tests do not click or type on your real Mac.
- These tests still use the real LLM, so they require network access and API credits.
- The mocked screenshots include descriptive text so the planner can reason over a deterministic fake screen state.
- If the model behaves poorly, fix the planner prompt or tool schema first before changing the executor.

### Troubleshooting

If you see an Anthropic authentication error:

- make sure `ANTHROPIC_API_KEY` is set in the same shell session

If the planner loops too long:

- lower `--max-iterations`
- inspect the printed `tool_history`
- tighten the planner prompt

If you want to change the fake desktop behavior:

- edit `src/agent/mock_executor.py`
