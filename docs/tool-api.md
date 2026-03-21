# Tool API

## Purpose

This document defines the execution API that the reasoning agent calls to control the Mac. These tools are intentionally low-level. The planner composes them into higher-level behaviors.

For v1, keep perception and action tools separate so the team can build and test each piece independently. It is acceptable if the common loop is temporarily more verbose.

Later, if latency or cost becomes a problem, these primitives can be merged behind the same planner-facing contract into combined tools such as "observe and click" or "observe and type". That optimization is explicitly deferred for now.

## Conventions

### Response envelope

All tools should return:

```json
{
  "ok": true,
  "tool": "tool_name",
  "result": {}
}
```

On failure:

```json
{
  "ok": false,
  "tool": "tool_name",
  "error": {
    "code": "NOT_FOUND",
    "message": "Search box not visible"
  }
}
```

### Coordinates

- Origin: top-left of the active display
- Units: device-independent screen pixels
- Bounding boxes use `{ "x": 0, "y": 0, "width": 0, "height": 0 }`

### Timing

- Every action should support a short timeout
- Long workflows should be broken into multiple tool calls

## Core Perception Tools

### `capture_screen`

Capture the current visible display or active window.

Request:

```json
{
  "tool": "capture_screen",
  "args": {
    "target": "display",
    "display_id": "main",
    "include_cursor": false
  }
}
```

Response:

```json
{
  "ok": true,
  "tool": "capture_screen",
  "result": {
    "image_id": "img_001",
    "width": 1440,
    "height": 900
  }
}
```

### `analyze_screen`

Run OCR and UI detection on a screenshot. Useful for finding text, buttons, icons, and likely interaction regions.

Request:

```json
{
  "tool": "analyze_screen",
  "args": {
    "image_id": "img_001",
    "include_ocr": true,
    "include_icons": true,
    "include_regions": true
  }
}
```

Response:

```json
{
  "ok": true,
  "tool": "analyze_screen",
  "result": {
    "text": [
      {
        "value": "Search",
        "bbox": { "x": 720, "y": 108, "width": 180, "height": 40 },
        "confidence": 0.96
      }
    ],
    "regions": [
      {
        "label": "search_input",
        "bbox": { "x": 701, "y": 101, "width": 260, "height": 48 },
        "confidence": 0.82
      }
    ]
  }
}
```

### `find_target`

Resolve a target from the current screen using a semantic query.

Request:

```json
{
  "tool": "find_target",
  "args": {
    "image_id": "img_001",
    "query": "YouTube search box",
    "match_text": ["Search"],
    "match_role": ["input", "button"]
  }
}
```

Response:

```json
{
  "ok": true,
  "tool": "find_target",
  "result": {
    "target_id": "target_search_box",
    "bbox": { "x": 701, "y": 101, "width": 260, "height": 48 },
    "center": { "x": 831, "y": 125 },
    "confidence": 0.91
  }
}
```

## Core Action Tools

### `click`

Click a point or target.

Request:

```json
{
  "tool": "click",
  "args": {
    "x": 831,
    "y": 125,
    "button": "left",
    "click_count": 1
  }
}
```

Alternative request:

```json
{
  "tool": "click",
  "args": {
    "target_id": "target_search_box",
    "button": "left",
    "click_count": 1
  }
}
```

### `scroll`

Scroll the active area.

Request:

```json
{
  "tool": "scroll",
  "args": {
    "direction": "down",
    "amount": 600,
    "granularity": "pixel"
  }
}
```

Notes:

- `amount` can be pixels, lines, or steps depending on `granularity`
- For YouTube feed scrolling, pixel scrolling is usually easiest

### `type_text`

Type text into the currently focused input.

Request:

```json
{
  "tool": "type_text",
  "args": {
    "text": "lofi hip hop",
    "clear_first": false
  }
}
```

### `press_key`

Press a key or key combination.

Request:

```json
{
  "tool": "press_key",
  "args": {
    "key": "ENTER",
    "modifiers": []
  }
}
```

Examples:

- `SPACE`
- `ESCAPE`
- `TAB`
- `CMD+L` can be represented as `key: "L", modifiers: ["CMD"]`
- YouTube fullscreen often maps to `F`

### `move_pointer`

Move the pointer without clicking.

Request:

```json
{
  "tool": "move_pointer",
  "args": {
    "x": 1050,
    "y": 640
  }
}
```

Useful when hover reveals hidden controls.



Pause to allow UI changes to settle.

Request:

```json
{
  "tool": "wait",
  "args": {
    "ms": 500
  }
}
```

## Optional Mac-Aware Tools

These are not required for the first prototype, but they will reduce failure rates.

### `get_frontmost_app`

Return the currently focused application.

### `list_windows`

Return visible windows and bounds.

### `focus_app`

Bring a known app to the foreground.

### `ax_find`

Use MacOS Accessibility APIs to find UI elements by role, label, or hierarchy.

### `ax_action`

Invoke an Accessibility action such as press, focus, or set value.

These tools are especially useful if browser controls are accessible through native APIs.

## Recommended Minimal v1 Set

If you want the smallest viable API for the demo, start with:

1. `capture_screen`
2. `analyze_screen`
3. `find_target`
4. `click`
5. `scroll`
6. `type_text`
7. `press_key`
8. `wait`

This is enough to support:

- search on YouTube
- feed scrolling
- result clicking
- pause and fullscreen shortcuts

This minimal set is intentionally primitive. The first implementation should optimize for clarity and parallel development, not for the fewest possible round trips.

## v1 Implementation Note

For the current build, assume:

- screenshot capture remains a separate tool call
- screen analysis remains a separate tool call
- target finding remains a separate tool call
- actions such as click, scroll, type, and key press remain separate tool calls

This makes it easier for different developers to work on perception and execution independently.

Merged tools are a later optimization, not a v1 requirement.

## Error Codes

Suggested normalized error codes:

- `NOT_FOUND`
- `LOW_CONFIDENCE`
- `PERMISSION_DENIED`
- `INVALID_ARGUMENT`
- `ACTION_FAILED`
- `TIMEOUT`
- `APP_NOT_FOCUSED`

## Planner Guidance

The reasoning agent should prefer this loop:

1. capture
2. analyze or find
3. act
4. verify

It should avoid issuing more than one irreversible action without re-checking the screen.

In v1, that may mean multiple separate tool calls for a single user intent. That is acceptable. Once the primitive tools are stable, the same loop can be accelerated by combining repeated perception and action sequences inside the executor.
