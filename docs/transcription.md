# Transcription

## Goal

Run transcription continuously for the full lifetime of the app and hand finalized spoken commands to the reasoning agent with minimal delay.

For the hackathon version, we can explicitly optimize for simplicity over battery, CPU, or network cost.

## Desired Behavior

When the app starts:

1. microphone capture starts
2. transcription starts immediately
3. partial transcript updates are produced as the user speaks
4. a final transcript event is emitted when the utterance is complete
5. the final transcript is forwarded to `Antique Hornet`

The planner should only receive finalized utterances for action-taking unless you deliberately want interrupt-style behavior later.

## Recommended Split

### Transcription runtime

Owns:

- microphone access
- streaming speech-to-text
- partial transcript buffering
- end-of-utterance detection
- finalized transcript emission

Does not own:

- UI planning
- screen analysis
- click or scroll execution

### Antique Hornet

Owns:

- interpreting the transcript as a command
- deciding whether it is actionable
- translating it into tool calls

## Why This Split Matters

If the transcription layer starts doing command interpretation, the architecture becomes harder to debug.

Clean separation is better:

- transcription answers: "what did the user say?"
- planner answers: "what should the computer do?"
- executor answers: "how do we perform the action?"

## Event Model

The cleanest interface is an utterance event stream.

### Partial transcript event

Useful for UI display only.

```json
{
  "type": "transcript.partial",
  "transcript_id": "tx_001",
  "text": "search for a youtube",
  "is_final": false,
  "started_at": "2026-03-21T12:00:00-07:00",
  "updated_at": "2026-03-21T12:00:01-07:00",
  "source": "microphone"
}
```

### Final transcript event

This is the main handoff into the agent.

```json
{
  "type": "transcript.final",
  "transcript_id": "tx_001",
  "text": "search for a youtube video about antique restoration",
  "is_final": true,
  "started_at": "2026-03-21T12:00:00-07:00",
  "ended_at": "2026-03-21T12:00:03-07:00",
  "source": "microphone"
}
```

### Agent handoff event

If you want a slightly richer envelope between transcription and planning, use:

```json
{
  "type": "agent.command",
  "command_id": "cmd_001",
  "transcript_id": "tx_001",
  "text": "search for a youtube video about antique restoration",
  "context": {
    "frontmost_app": "Google Chrome"
  }
}
```

## Minimal API Surface

You do not need many methods for v1. A simple runtime interface is enough:

### `start_transcription`

Start always-on microphone transcription.

Example response:

```json
{
  "ok": true,
  "state": "running"
}
```

### `stop_transcription`

Stop microphone capture and transcription.

### `get_transcription_state`

Return status details such as:

- running or stopped
- current transcript id
- last partial text
- last final transcript id

### `subscribe_transcripts`

Stream `transcript.partial` and `transcript.final` events to the app.

In many implementations this is not a literal function call. It may just be an event emitter, callback, websocket, or async stream.

## Command Boundary Detection

You need a way to decide when speech becomes a command to send to the planner.

For the hackathon version, the simplest acceptable approach is:

- stream partial transcripts live
- finalize when silence exceeds a short threshold
- send only the final transcript to `Antique Hornet`

This is enough for commands like:

- "scroll down"
- "pause"
- "search for synthwave mixes"

You can add wake words or push-to-talk later if false activations become a problem.

## Recommended v1 Assumptions

- transcription runs 24/7 while the app is open
- only one microphone source
- only one active user
- no battery optimization
- no offline mode requirement
- final transcript triggers agent reasoning
- partial transcript is optional UI polish, not required for control

## Example End-To-End Flow

User says:

`search for lofi hip hop`

System behavior:

1. transcription runtime emits partials as the user speaks
2. silence is detected
3. transcription runtime emits `transcript.final`
4. app forwards that final transcript to `Antique Hornet`
5. `Antique Hornet` inspects the screen and decides the next tool call
6. `Handy Crab` executes the tool call

## Open Questions For Later

These do not need to be solved now, but they will matter after the hackathon prototype:

- how to avoid accidental background activation
- whether to support interruption while the agent is mid-task
- whether partial transcripts should ever alter execution
- whether commands should be queued or cancel current work
- whether a wake word is needed
