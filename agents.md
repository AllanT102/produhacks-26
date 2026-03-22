# Agents

## Goal

Build a voice-driven Mac control system that can:

- listen continuously
- transcribe speech into short commands
- show clear UI feedback while the system is active
- execute browser and desktop actions

The first-class demo is browser control on macOS, especially YouTube-style flows, but the current implementation is best understood as a browser-first agent loop rather than a full general desktop agent.

## Current System

The current codebase is simpler than the original architecture sketch.

Today the main runtime is:

1. transcription runtime
2. finalized transcript handoff
3. single agent loop
4. browser-use planner/backend
5. overlay feedback

There is not currently a separate lightweight command router in the main execution path.

## Current Flow

### 0. Transcription Runtime

Supported backends:

- local `faster-whisper`
- ElevenLabs realtime STT over WebSockets

Responsibilities:

- capture microphone audio continuously
- emit partial transcripts for UI/debug feedback
- emit final transcripts for execution
- forward final transcripts into the agent queue

Important current behavior:

- partial transcripts are visible but are not executed
- only final transcripts go into the agent loop
- a short duplicate suppression window prevents the same finalized transcript from being executed repeatedly

### 1. Agent Loop

The agent loop is currently very thin.

Responsibilities:

- consume finalized `AgentCommand` items
- update the overlay state (`Listening`, `Tinkering`, `Ready`, `Stopped`, `Error`)
- call the planner
- support stop/cancel through `AgentController`

The loop does not currently do:

- fast routing for trivial commands
- multi-step local desktop planning
- structured inspect/act/verify over screenshots

### 2. Planner

The current planner is effectively a browser-use adapter.

Responsibilities:

- decide whether browser-use is available
- route the command into the warm browser-use backend
- return the resulting summary

This means the current planner is not a general reasoning layer over a stable local tool API. It is mostly a wrapper around a persistent browser-use session.

### 3. Browser Backend

The current browser backend uses a warm persistent browser-use server.

It:

- keeps a browser-use server process alive
- reuses browser state across commands
- can attach to a Chrome CDP session if configured
- tries a direct browser helper path first
- falls back to a browser-use agent path when the direct helper cannot handle the command

This fallback is the main source of high latency.

## What Is Actually Slow

The biggest latency source right now is browser-use agent fallback, not the overlay and not transcript transport.

When a command misses the direct browser helper and falls into the browser-use agent path, the system can spend tens of seconds in one command.

Typical expensive path:

1. final transcript arrives
2. agent loop hands it to planner
3. planner routes into browser-use
4. browser-use direct helper cannot handle the utterance
5. browser-use agent fallback runs against Anthropic
6. result returns after several seconds or tens of seconds

That is why the loop can feel unusable even when transcription itself is working.

## Current Failure Modes

### 1. Browser-use fallback is too slow

Open-ended commands can be reasonable.

Simple commands can still become expensive if the command parser misses them and falls through to the full browser-use agent path.

### 2. Transcript wording is noisy

Even with ElevenLabs, natural speech can produce:

- repeated phrasing
- background chatter
- imperfect proper nouns

If a bad final transcript is committed, the current system still tries to execute it.

### 3. The system is browser-first, not truly general yet

The current architecture can control a browser well enough for demos, but it is not yet a mature desktop agent with robust screenshot-grounded action selection.

## Current Architecture Boundaries

What the system is today:

- a transcription layer
- a queue-based command handoff
- a browser-first execution agent
- an overlay UI for state feedback

What the system is not yet:

- a full planner over local Mac action primitives
- a reliable screenshot-grounded desktop manipulation loop
- a generalized executor for arbitrary Mac UI tasks

## Browser-Use Status

Browser-use is currently central to the execution path when enabled.

If `BROWSER_USE_ENABLED=1`:

- finalized commands route into the browser-use-backed planner
- direct browser helper logic may handle some commands quickly
- anything unsupported falls back to the slower agent path

If `BROWSER_USE_ENABLED=0`:

- the current planner returns that browser-use is unavailable
- there is no equivalent full local planner path at the moment

So, in the current repo, browser-use is not just an experiment. It is effectively the main planner backend when enabled.

## Overlay State Model

The overlay should behave like this:

1. `Listening`
2. partial transcript expands the pill
3. final transcript arrives
4. `Tinkering` while the agent is executing
5. `Ready`
6. back to `Listening`

Transient states:

- `Stopped`
- `Error`

These should settle back to `Listening` after a short delay.

## What Needs To Improve Next

Priority order:

1. make browser-use fallback rarer
2. make browser commands more structured before they reach browser-use
3. improve transcript quality and command normalization
4. restore a real local planner/executor path if the goal is general Mac control
5. keep the overlay quiet and trustworthy

## Recommended Near-Term Direction

If the goal is a usable hackathon demo, the highest-leverage path is:

1. keep ElevenLabs for transcription
2. keep the warm browser-use backend
3. improve browser command parsing so obvious commands do not hit the expensive fallback
4. document clearly that the current product is browser-first

If the goal is a true general computer-use agent, then the architecture needs to move back toward:

- planner over stable tool primitives
- local executor
- screenshot/accessibility grounding
- inspect/act/verify loops

That is not the current state of the repo, and this document should reflect that honestly.
