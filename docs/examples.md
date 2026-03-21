# Example Flows

These examples assume the current v1 architecture where perception and action remain separate tool calls. Some flows are more verbose than a future optimized version, but they are easier to build, test, and debug now.

## 1. Search YouTube For A Video

Voice command:

`search for handy crab documentary`

Possible action loop:

```json
[
  {
    "tool": "capture_screen",
    "args": {
      "target": "display",
      "display_id": "main"
    }
  },
  {
    "tool": "find_target",
    "args": {
      "image_id": "img_001",
      "query": "YouTube search box",
      "match_text": ["Search"]
    }
  },
  {
    "tool": "click",
    "args": {
      "target_id": "target_search_box"
    }
  },
  {
    "tool": "type_text",
    "args": {
      "text": "handy crab documentary"
    }
  },
  {
    "tool": "press_key",
    "args": {
      "key": "ENTER",
      "modifiers": []
    }
  }
]
```

## 2. Scroll YouTube Feed

Voice command:

`scroll down a bit`

Possible action loop:

```json
[
  {
    "tool": "scroll",
    "args": {
      "direction": "down",
      "amount": 500,
      "granularity": "pixel"
    }
  },
  {
    "tool": "wait",
    "args": {
      "ms": 250
    }
  },
  {
    "tool": "capture_screen",
    "args": {
      "target": "display",
      "display_id": "main"
    }
  }
]
```

## 3. Open The First Search Result

Voice command:

`open the first result`

Possible action loop:

```json
[
  {
    "tool": "capture_screen",
    "args": {
      "target": "display",
      "display_id": "main"
    }
  },
  {
    "tool": "find_target",
    "args": {
      "image_id": "img_002",
      "query": "first YouTube video result"
    }
  },
  {
    "tool": "click",
    "args": {
      "target_id": "target_first_result"
    }
  }
]
```

## 4. Pause The Current Video

Voice command:

`pause`

Possible v1 action:

```json
{
  "tool": "press_key",
  "args": {
    "key": "SPACE",
    "modifiers": []
  }
}
```

Possible fallback:

```json
[
  {
    "tool": "move_pointer",
    "args": {
      "x": 900,
      "y": 500
    }
  },
  {
    "tool": "capture_screen",
    "args": {
      "target": "display",
      "display_id": "main"
    }
  },
  {
    "tool": "find_target",
    "args": {
      "image_id": "img_003",
      "query": "pause button on YouTube player"
    }
  },
  {
    "tool": "click",
    "args": {
      "target_id": "target_pause_button"
    }
  }
]
```

## 5. Keep Scrolling Until A Condition Is True

Voice command:

`keep scrolling until you see live videos`

Planner strategy:

1. scroll down
2. capture screen
3. analyze OCR for `Live` or `LIVE`
4. stop when match confidence is high
5. otherwise repeat with a loop limit

This is a planner concern, not a primitive tool concern.

## Recommended Planner Prompt Shape

If you later prompt the reasoning agent directly, a good shape is:

```text
You are a screen-aware planner for Mac control.
You can only act by calling the provided tools.
Take one small action at a time.
After each action that may change the UI, verify the screen again.
Prefer keyboard shortcuts when they are reliable.
If target confidence is low, inspect the screen instead of guessing.
The user goal is: <voice transcript here>
```

For v1, it is fine if a single task requires several primitive tool calls such as capture, analyze, find, and click. Merged tools can be added later without changing the planner's high-level loop.
