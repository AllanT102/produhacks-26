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

- whether the system is listening, thinking, speaking, ready, or stopped
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

`run-mock` now injects a one-shot fake transcript from the terminal instead of running the live microphone loop with a fake transcriber.

Example:

```bash
FAKE_TRANSCRIPT_TEXT="search youtube for trimentorship and play the first video" make run-mock
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

### Run with ElevenLabs realtime transcription

Set your API key first:

```bash
export ELEVENLABS_API_KEY=your_key_here
```

Then run:

```bash
make run-elevenlabs
```

Optional tuning:

```bash
ELEVENLABS_PREVIOUS_TEXT="Mac voice control and YouTube commands." make run-elevenlabs
```

This backend uses ElevenLabs realtime speech-to-text over WebSockets instead of the local Whisper loop.

The app entry point logs transcript events and sends finalized commands into a simple agent loop.
It also launches the desktop overlay automatically.
If `PyObjC` is not installed yet, the app falls back to headless mode and prints a warning.

### Run in dev type mode

```bash
make run-type
```

or

```bash
./scripts/run_type.sh
```

This mode disables microphone input and lets you type commands directly into the terminal with a `type>` prompt. It is the best mode for debugging planner and browser behavior without transcription noise.

### Run in Wispr mode

```bash
make run-wispr
```

This mode opens the native overlay with an actual text input field. Click the field once, dictate into it with Wispr, then press Return or click `Send`. Unlike `run-mock`, it stays alive for repeated commands.

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

## Browser Behavior

By default, browser commands now use the local macOS + Chrome tool path:

- `open_app` uses `open -a`, which reuses the existing app instance
- Chrome interactions use the Apple Events browser tools in `src/tool_runtime/tools/browser.py`
- explicit `read ...` voice commands use a direct page-text extraction path and ElevenLabs TTS instead of browser-use fallback when `ELEVENLABS_API_KEY` is available

### Generic Direct Browser Commands

The direct helper now covers a broader set of site-agnostic interactions before anything falls back to slower planning. Supported command shapes include:

- navigation: `open github`, `search for lo-fi beats on youtube`, `back`, `forward`, `reload`, `go home`
- tabs and browser surfaces: `new tab`, `close tab`, `duplicate tab`, `next tab`, `go to tab 3`, `open history`, `open downloads`, `open bookmarks`
- scrolling and focus: `scroll down`, `scroll to comments`, `go to top`, `focus address bar`
- ranked clicks: `click the first result`, `open the third link in a new tab`, `click the second button`
- generic click targets: `click continue`, `open view profile`, `accept cookies`, `dismiss popup`
- text entry: `type hello in search box`, `fill email with jay@example.com`, `fill message with sounds good and submit`
- active-field dictation: `type sounds good`, `write thanks for the update`
- selection controls: `select United States from country`, `set sort to newest`, `check remember me`, `uncheck email updates`
- key presses and quick actions: `press command l`, `submit`, `escape`, `zoom in`, `zoom out`, `reset zoom`

The heavier `browser-use` backend is now opt-in only. To enable it explicitly:

```bash
BROWSER_USE_ENABLED=1 make run-whisper
```

Leaving it off avoids slow browser-use startup and avoids launching a separate automation-driven browser session for normal commands.

### Reuse Existing Chrome With Browser-Use

If you want Browser Use to attach to an existing Chrome debugging session instead of launching its own managed browser, start Chrome with a remote debugging port and set `BROWSER_USE_CDP_URL`.

Example:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

Then run:

```bash
BROWSER_USE_ENABLED=1 BROWSER_USE_CDP_URL=http://127.0.0.1:9222 make run-whisper
```

With that setup:

- Browser Use attaches to the existing Chrome session
- the browser-use server keeps the browser session alive
- follow-up browser commands can reuse the same browser context

This is the best path if you want Browser Use for high-level navigation while still keeping a more natural browser experience.

## Read Aloud

The agent can now speak page content back to you, but only for explicit readback commands. Supported command shapes include:

- `read this page aloud`
- `read this to me`
- `read the selected text`
- `read the title`
- `read the first paragraph`

Current behavior:

- readback is handled before browser-use, so it stays on a fast direct path
- text is extracted from the active Google Chrome tab
- the overlay switches to `Speaking` while TTS is running
- live microphone transcripts are suppressed during speech, plus a short cooldown, to avoid the agent transcribing itself

Notes:

- `read this` prefers the current text selection and falls back to the top of the page if nothing is selected
- full pages are trimmed to the beginning instead of reading arbitrarily long content forever
- Chrome still needs `Allow JavaScript from Apple Events` enabled for the browser extraction helpers to work
- TTS defaults to ElevenLabs when `ELEVENLABS_API_KEY` is set; override with `AGENT_TTS_PROVIDER=say` if you explicitly want the macOS fallback
- you can override the voice with `ELEVENLABS_TTS_VOICE_ID` or `ELEVENLABS_TTS_VOICE_NAME`
- speech speed defaults slightly faster than normal; tune it with `ELEVENLABS_TTS_SPEED` such as `1.2`
- `Stop` cancels the current readback, including active playback and best-effort in-flight ElevenLabs synthesis

## Planner Speed

The planner now uses two profiles:

- fast profile for normal short voice commands
- deep fallback only when the fast pass stalls

Before the planner runs, the app also uses a generic direct-command router for low-latency primitives such as:

- opening an app or URL
- scrolling up or down
- play/pause
- mute and volume changes
- brightness changes

Only non-trivial commands fall through to the general planner.

Default env vars:

```bash
ANTHROPIC_FAST_MODEL=claude-sonnet-4-20250514
ANTHROPIC_FAST_MAX_TOKENS=700
ANTHROPIC_FAST_MAX_ITERATIONS=5
ANTHROPIC_DEEP_MODEL=claude-opus-4-20250514
ANTHROPIC_DEEP_MAX_TOKENS=1200
ANTHROPIC_DEEP_MAX_ITERATIONS=10
```

If you want the snappiest possible behavior, keep your normal app runs on the fast profile and only use the deep fallback for harder tasks.

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
