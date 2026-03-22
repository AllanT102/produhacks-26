# Agents

## Goal

Build a voice-driven Mac control system that feels immediate in the common case and still general enough to control arbitrary desktop and browser workflows.

The system should not depend on site-specific hardcoded flows for normal operation. It should rely on:

- a fast transcription layer
- a lightweight command router
- a general planner over tools
- a deterministic executor

## Current Reality

The main usability problem is latency, not capability.

A voice control loop feels broken if:

- the first action starts after 5 to 20 seconds
- every browser command launches a separate automation browser session
- the planner spends multiple expensive LLM rounds discovering obvious actions

The architecture should therefore optimize for:

1. fast first action
2. generic tool use
3. minimal planner rounds
4. deterministic execution

## Recommended System Shape

### 0. Transcription Runtime

Responsibilities:

- capture microphone audio continuously
- emit partial transcripts for UI only
- emit final transcripts for execution
- hand final transcripts to the command router

This layer should not decide what action to take.

### 1. Command Router

Responsibilities:

- classify the utterance quickly
- decide whether the command is:
  - a direct primitive
  - a browser task
  - a desktop task
  - a planner task
- choose the cheapest valid execution path

This layer should be fast and shallow. It is not a full planner.

Examples of direct primitives:

- `stop`
- `scroll down`
- `scroll up`
- `pause`
- `open chrome`
- `open youtube.com`
- `volume up`
- `brightness down`

These are generic commands, not app-specific hacks.

### 2. Planner

Responsibilities:

- interpret non-trivial commands
- inspect screen and browser state
- choose the next tool call
- verify outcomes
- stop as soon as the goal is achieved

The planner should stay generic.

It should not contain lots of:

- YouTube-specific flows
- LinkedIn-specific flows
- one-off scripted action chains

Those make demos look good briefly but do not scale to a real computer-use agent.

### 3. Executor

Responsibilities:

- run desktop and browser tools
- return structured results
- handle clicks, typing, scrolling, key presses, screenshots, and browser DOM actions

This layer should be deterministic and fast.

## Browser Strategy

There should be two browser paths:

### Local Browser Tools

Default path.

Use:

- `open_app`
- `browser_get_page`
- `browser_query`
- `browser_click_ref`
- `browser_fill_ref`
- `browser_scroll_to_text`

This path should reuse the user’s existing Chrome app and tabs through normal macOS behavior and Chrome Apple Events.

### Browser-Use Backend

Optional path only.

Use only when explicitly enabled or when running controlled experiments.

It should not be the default path for normal voice control because it can add:

- startup latency
- separate browser automation state
- a less natural user experience

## Are We Currently Using Browser-Use?

Not by default.

In the current code:

- `browser-use` is only considered when `BROWSER_USE_ENABLED=1`
- with `BROWSER_USE_ENABLED=0`, the app should stay on the local browser/tool path

So if the loop is still slow with `BROWSER_USE_ENABLED=0`, that slowness is coming from the planner model and planner round-trip, not from `browser-use`.

## Why The Current Loop Feels Slow

The main bottleneck is the planner round itself.

A typical slow path looks like:

1. transcript arrives
2. planner takes a screenshot
3. planner sends a full LLM request
4. LLM thinks for several seconds
5. planner takes one action
6. planner sends another full LLM request

That is too expensive for voice control.

## Make The Loop Usable

### 1. Add a real fast router

Before the planner, route obvious commands directly.

Good direct routes:

- stop/cancel
- open app
- open URL
- simple scroll
- simple media keys
- simple brightness and volume commands

This removes many LLM calls entirely.

### 2. Keep the planner generic

Do not solve latency by hardcoding app-specific flows.

Instead:

- improve the browser tools
- improve the planner prompt
- lower planner latency
- reduce the number of planner rounds

### 3. Use a fast planner profile first

Default planner behavior should be:

- fast model
- low token budget
- small iteration budget

Then only escalate to a stronger model if the fast attempt stalls.

### 4. Reduce planner rounds

The planner should aim for:

- 0 LLM rounds for direct commands
- 1 to 2 LLM rounds for common browser tasks
- more only when genuinely necessary

### 5. Improve tool grounding

The planner gets slow when the tools are weak.

The best way to speed it up is not just changing models, but giving it better primitives:

- reliable browser DOM querying
- direct browser field fill
- direct browser link click
- browser page metadata
- direct app open and URL open
- propose-targets for desktop UI

Better tools mean fewer planner turns.

## Practical Latency Budget

For a usable voice experience:

- transcript finalization: under 1s after speech ends
- direct command execution start: under 300ms
- planner-based action start: ideally under 2s
- browser-use path: opt-in only, because it may be much slower

If a path consistently starts acting after 5s or more, it should not be the default.

## Recommended Loop

1. user speaks
2. transcription runtime emits final transcript
3. command router classifies the request
4. if direct primitive:
   execute immediately
5. otherwise:
   run planner on current browser or desktop state
6. executor performs tool call
7. planner verifies result
8. stop as soon as goal is satisfied

## What To Build Next

Priority order:

1. generic direct-command router
2. stronger browser primitives
3. faster default planner profile
4. deep fallback only when needed
5. keep browser-use behind an explicit flag

This is the version of the architecture that is both:

- realistic for a general computer-use agent
- fast enough to feel usable in a voice interface
