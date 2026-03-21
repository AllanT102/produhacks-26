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
