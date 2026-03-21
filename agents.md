# Agents

## Goal

Build a voice-driven Mac control system that can understand a spoken request, reason over the current screen, and execute UI actions such as scroll, click, type, and keyboard shortcuts.

The core demo flow is YouTube control:

- "Scroll down"
- "Search for lo-fi beats"
- "Open the first result"
- "Pause"
- "Go fullscreen"

The system should behave like a general computer-use agent, but the first-class experience is browsing and controlling YouTube with voice.

## System Shape

The system is easiest to reason about as three cooperating layers:

### 0. Transcription Runtime

The app should include an always-on transcription runtime that starts when the app launches and can run continuously in the background.

Responsibilities:

- capture microphone audio continuously
- produce partial and final transcripts
- detect likely command boundaries
- forward finalized commands to `Antique Hornet`
- stay simple and always-on for the hackathon version

This layer is not the reasoning agent. Its job is to turn raw speech into structured utterance events that the planner can consume.

### 1. Antique Hornet

`Antique Hornet` is the reasoning and planning agent.

Responsibilities:

- Accept a natural-language voice command transcript
- Track short-lived task context
- Inspect screen state via perception tools
- Decide the next UI action
- Call tool APIs
- Recover from uncertainty by re-checking the screen
- Stop when the task is complete or when confidence is too low

This agent should not directly contain platform-specific automation code. It should produce structured tool calls against a stable API.

### 2. Handy Crab

`Handy Crab` is the execution layer.

Responsibilities:

- Receive structured tool calls
- Execute MacOS interactions
- Return structured results
- Capture screenshots and element candidates
- Report failures, timing issues, and missing permissions

This layer is the bridge to the operating system. It owns coordinate systems, accessibility calls, mouse movement, key events, scrolling, and screen capture.

## High-Level Flow

1. User speaks a command.
2. The always-on transcription runtime captures audio and emits partial transcript updates.
3. When the utterance is complete, the transcription runtime emits a final transcript event.
4. `Antique Hornet` receives the final transcript plus recent task context.
5. `Antique Hornet` calls perception tools to inspect the current screen.
6. `Antique Hornet` plans one small next step.
7. `Handy Crab` executes the requested tool call.
8. The system re-checks the screen if the action changed UI state.
9. The loop repeats until success, failure, or escalation.

## Design Principles

### Use small reversible steps

The agent should prefer:

- inspect
- act
- verify

over long blind action chains.

### Keep tools primitive

The execution API should expose simple building blocks:

- screenshot
- click
- scroll
- type
- key press
- wait
- locate text or icon on screen

The reasoning agent composes these primitives into behaviors.

### Prefer grounding over guesswork

Before clicking, the agent should usually know one of:

- exact coordinates
- a bounding box
- a text match
- an accessibility node

If confidence is low, it should re-capture the screen instead of guessing.

### Optimize for latency in the common loop

For YouTube browsing, the hot path should be:

- hear transcript
- finalize utterance
- inspect visible UI
- take one action
- verify result

The system does not need deep multi-minute planning. It needs fast short-horizon control.

### Keep transcription separate from planning

The always-on listener should not decide UI actions itself. It should only:

- listen
- segment speech
- produce transcript events
- hand off finalized commands

This keeps the architecture clean:

- transcription runtime handles audio
- `Antique Hornet` handles reasoning
- `Handy Crab` handles execution

## Key Use Cases

### YouTube scrolling

Examples:

- "Scroll down a bit"
- "Scroll faster"
- "Go back up"
- "Keep scrolling until you see music videos"

This requires:

- active window awareness
- scroll direction and magnitude
- optional repeated scrolling with stop conditions

### YouTube search

Examples:

- "Search for antique restoration videos"
- "Click the third result"
- "Open Shorts"

This requires:

- text field targeting
- click and type
- submit actions
- result disambiguation

### Media control

Examples:

- "Pause"
- "Mute"
- "Go fullscreen"
- "Skip ahead ten seconds"

This requires:

- keyboard shortcuts when available
- fallback click targeting on visible controls

## Agent State

The reasoning agent should keep a small working memory:

- latest transcript
- transcript id
- current goal
- last few tool calls
- last screenshot reference
- active app or tab if known
- unresolved ambiguity

It should avoid long-term memory unless explicitly needed.

## Failure Modes

Expected failure cases:

- screen changed before the click executed
- target not visible
- wrong window focused
- YouTube layout differs from expectation
- missing Accessibility or Screen Recording permissions
- speech transcript is ambiguous

Recovery strategy:

1. verify current screen
2. attempt one fallback
3. ask for clarification or surface failure

## Suggested Agent Contract

The reasoning layer should emit actions in a structured format like:

```json
{
  "tool": "click",
  "args": {
    "x": 812,
    "y": 214,
    "button": "left"
  },
  "why": "Focus the YouTube search box",
  "expected_outcome": "Text cursor appears in the search field"
}
```

The transcription runtime should hand work to the reasoning layer in a structured format like:

```json
{
  "transcript_id": "tx_001",
  "text": "scroll down a bit",
  "is_final": true,
  "started_at": "2026-03-21T12:00:00-07:00",
  "ended_at": "2026-03-21T12:00:02-07:00",
  "source": "microphone"
}
```

Execution responses should also be structured:

```json
{
  "ok": true,
  "tool": "click",
  "result": {
    "timestamp": "2026-03-21T12:00:00-07:00"
  }
}
```

## Scope Boundary

In v1, this project should focus on:

- one-user local Mac control
- one active display, with optional future multi-display support
- YouTube browsing and playback flows
- screen-driven control with optional accessibility enhancement

Out of scope for v1:

- remote control
- multi-user coordination
- full desktop autonomy
- background task automation without user initiation

## Implementation Note

Treat `Antique Hornet` as a planner over an explicit tool API and `Handy Crab` as a deterministic Mac automation runtime. This separation keeps prompts stable, makes tool behavior testable, and allows the execution layer to be swapped later.

For the hackathon build, assume the microphone listener is active for the full app session and forwards finalized utterances immediately.

See [docs/transcription.md](/Users/jaypark/Documents/GitHub/produhacks-26/docs/transcription.md) for the speech pipeline, [docs/tool-api.md](/Users/jaypark/Documents/GitHub/produhacks-26/docs/tool-api.md) for the execution API, and [docs/examples.md](/Users/jaypark/Documents/GitHub/produhacks-26/docs/examples.md) for concrete task flows.
