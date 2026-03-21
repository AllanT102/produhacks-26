"""Grounded target proposal tools.

Combines multiple local target sources into one normalized candidate list:
- frontmost-app Accessibility elements
- Dock Accessibility elements for app icons
- OCR text boxes from the current screenshot when Vision is available
"""

from __future__ import annotations

import base64
import io
import re
import subprocess
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

from src.tool_runtime.tools.click import click, double_click

_TARGET_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL_SECONDS = 120.0


def _cleanup_cache() -> None:
    now = time.time()
    expired = [
        target_id for target_id, payload in _TARGET_CACHE.items()
        if now - payload.get("created_at", now) > _CACHE_TTL_SECONDS
    ]
    for target_id in expired:
        _TARGET_CACHE.pop(target_id, None)


def _tokenize(text: str) -> List[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if token]


def _clean_osascript_atom(value: str) -> str:
    return value.strip().strip("{}").strip().strip('"').strip()


def _score_candidate(query: str, candidate: Dict[str, Any]) -> float:
    query_tokens = set(_tokenize(query))
    haystack = " ".join(
        str(candidate.get(key, "")) for key in ("label", "description", "role", "app_name", "source")
    ).lower()
    hay_tokens = set(_tokenize(haystack))

    if not query_tokens:
        return float(candidate.get("confidence", 0.0))

    overlap = len(query_tokens & hay_tokens)
    substring_bonus = 1.0 if query.lower() in haystack else 0.0
    confidence = float(candidate.get("confidence", 0.0))
    return overlap * 10.0 + substring_bonus * 5.0 + confidence


def _make_bbox(x: float, y: float, width: float, height: float) -> Dict[str, int]:
    return {
        "x": int(round(x)),
        "y": int(round(y)),
        "width": max(1, int(round(width))),
        "height": max(1, int(round(height))),
    }


def _center_from_bbox(bbox: Dict[str, int]) -> Dict[str, int]:
    return {
        "x": bbox["x"] + bbox["width"] // 2,
        "y": bbox["y"] + bbox["height"] // 2,
    }


def _cache_targets(targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    _cleanup_cache()
    cached = []
    for target in targets:
        target_id = f"target_{uuid.uuid4().hex[:10]}"
        payload = dict(target)
        payload["target_id"] = target_id
        payload["created_at"] = time.time()
        _TARGET_CACHE[target_id] = payload
        cached.append({k: v for k, v in payload.items() if k != "created_at"})
    return cached


def _run_osascript(script: str, timeout: float = 1.5) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["osascript", "-ss", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "timed out"
    except Exception as exc:
        return False, str(exc)

    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        return False, message or "osascript failed"
    return True, result.stdout.strip()


def _parse_osascript_lines(raw: str, source: str, app_name: Optional[str] = None) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    if not raw:
        return candidates

    for line in raw.splitlines():
        parts = line.split("||")
        if len(parts) < 5:
            continue
        label = _clean_osascript_atom(parts[0])
        description = _clean_osascript_atom(parts[1])
        role = _clean_osascript_atom(parts[2])
        position = parts[3].strip()
        size = parts[4].strip()

        pos_match = re.search(r"(-?\d+)\s*,\s*(-?\d+)", position)
        size_match = re.search(r"(-?\d+)\s*,\s*(-?\d+)", size)
        if not pos_match or not size_match:
            continue

        x = float(pos_match.group(1))
        y = float(pos_match.group(2))
        width = float(size_match.group(1))
        height = float(size_match.group(2))
        if width <= 0 or height <= 0:
            continue

        bbox = _make_bbox(x, y, width, height)
        candidate = {
            "label": label or description or role or "unlabeled",
            "description": description,
            "role": role or "ui_element",
            "source": source,
            "bbox": bbox,
            "center": _center_from_bbox(bbox),
            "confidence": 0.95 if source.startswith("ax") else 0.85,
        }
        if app_name:
            candidate["app_name"] = app_name
        candidates.append(candidate)

    return candidates


def _parse_int_series(raw: str) -> List[int]:
    return [int(match) for match in re.findall(r"-?\d+", raw)]


def _collect_frontmost_ax_targets() -> List[Dict[str, Any]]:
    frontmost_script = """
tell application "System Events"
    return name of first application process whose frontmost is true
end tell
"""
    ok, app_name = _run_osascript(frontmost_script, timeout=1.0)
    if not ok or not app_name:
        return []

    script = f"""
set oldDelims to AppleScript's text item delimiters
set AppleScript's text item delimiters to linefeed
tell application "System Events"
    tell process "{app_name}"
        set outputLines to {{}}
        try
            set elementList to entire contents of front window
            repeat with e in elementList
                try
                    set elemName to ""
                    try
                        set elemName to name of e as text
                    end try
                    set elemDesc to ""
                    try
                        set elemDesc to description of e as text
                    end try
                    set elemRole to ""
                    try
                        set elemRole to role of e as text
                    end try
                    set elemPos to ""
                    try
                        set elemPos to ((item 1 of position of e) as text) & "," & ((item 2 of position of e) as text)
                    end try
                    set elemSize to ""
                    try
                        set elemSize to ((item 1 of size of e) as text) & "," & ((item 2 of size of e) as text)
                    end try
                    if elemPos is not "" and elemSize is not "" then
                        copy (elemName & "||" & elemDesc & "||" & elemRole & "||" & elemPos & "||" & elemSize) to end of outputLines
                    end if
                end try
            end repeat
        end try
        set outputText to outputLines as text
    end tell
end tell
set AppleScript's text item delimiters to oldDelims
return outputText
"""
    ok, raw = _run_osascript(script, timeout=2.0)
    if not ok:
        return []
    return _parse_osascript_lines(raw, source="ax_frontmost", app_name=app_name)


def _collect_dock_ax_targets() -> List[Dict[str, Any]]:
    names_script = """
tell application "System Events"
    tell process "Dock"
        return name of every UI element of list 1
    end tell
end tell
"""
    descriptions_script = """
tell application "System Events"
    tell process "Dock"
        return description of every UI element of list 1
    end tell
end tell
"""
    roles_script = """
tell application "System Events"
    tell process "Dock"
        return role of every UI element of list 1
    end tell
end tell
"""
    positions_script = """
tell application "System Events"
    tell process "Dock"
        return position of every UI element of list 1
    end tell
end tell
"""
    sizes_script = """
tell application "System Events"
    tell process "Dock"
        return size of every UI element of list 1
    end tell
end tell
"""

    ok_names, raw_names = _run_osascript(names_script, timeout=1.0)
    ok_desc, raw_desc = _run_osascript(descriptions_script, timeout=1.0)
    ok_roles, raw_roles = _run_osascript(roles_script, timeout=1.0)
    ok_pos, raw_pos = _run_osascript(positions_script, timeout=1.0)
    ok_sizes, raw_sizes = _run_osascript(sizes_script, timeout=1.0)
    if not all([ok_names, ok_desc, ok_roles, ok_pos, ok_sizes]):
        return []

    names = [_clean_osascript_atom(part) for part in raw_names.split(",")]
    descriptions = [_clean_osascript_atom(part) for part in raw_desc.split(",")]
    roles = [_clean_osascript_atom(part) for part in raw_roles.split(",")]
    positions = _parse_int_series(raw_pos)
    sizes = _parse_int_series(raw_sizes)

    count = min(
        len(names),
        len(descriptions),
        len(roles),
        len(positions) // 2,
        len(sizes) // 2,
    )
    candidates: List[Dict[str, Any]] = []
    for index in range(count):
        x = positions[index * 2]
        y = positions[index * 2 + 1]
        width = sizes[index * 2]
        height = sizes[index * 2 + 1]
        bbox = _make_bbox(x, y, width, height)
        candidates.append({
            "label": names[index] or descriptions[index] or roles[index] or "dock_item",
            "description": descriptions[index],
            "role": roles[index] or "AXDockItem",
            "source": "ax_dock",
            "app_name": "Dock",
            "bbox": bbox,
            "center": _center_from_bbox(bbox),
            "confidence": 0.95,
        })
    return candidates


def _collect_ocr_targets() -> List[Dict[str, Any]]:
    try:
        from AppKit import NSURL
        from Foundation import NSDictionary
        from Vision import VNImageRequestHandler, VNRecognizeTextRequest
        from src.tool_runtime.tools.screenshot import screenshot
    except Exception:
        return []

    shot = screenshot()
    if not shot.get("ok"):
        return []

    data_b64 = shot.get("data")
    if not data_b64:
        return []

    with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp_file:
        tmp_file.write(base64.b64decode(data_b64))
        tmp_file.flush()

        request = VNRecognizeTextRequest.alloc().init()
        if hasattr(request, "setRecognitionLevel_"):
            try:
                request.setRecognitionLevel_(1)
            except Exception:
                pass
        handler = VNImageRequestHandler.alloc().initWithURL_options_(
            NSURL.fileURLWithPath_(tmp_file.name),
            NSDictionary.dictionary(),
        )
        try:
            success = handler.performRequests_error_([request], None)
        except Exception:
            return []
        if isinstance(success, tuple) and len(success) >= 1 and not success[0]:
            return []

        results = request.results() or []

    candidates: List[Dict[str, Any]] = []
    image_width = int(shot.get("width", 0) or 0)
    image_height = int(shot.get("height", 0) or 0)
    if image_width <= 0 or image_height <= 0:
        try:
            from PIL import Image

            image = Image.open(io.BytesIO(base64.b64decode(data_b64)))
            image_width, image_height = image.size
        except Exception:
            return []

    for observation in results:
        try:
            top_candidate = observation.topCandidates_(1)[0]
            text = str(top_candidate.string())
            confidence = float(top_candidate.confidence())
            box = observation.boundingBox()
        except Exception:
            continue

        bbox = _make_bbox(
            box.origin.x * image_width,
            (1.0 - box.origin.y - box.size.height) * image_height,
            box.size.width * image_width,
            box.size.height * image_height,
        )
        candidates.append({
            "label": text,
            "description": text,
            "role": "ocr_text",
            "source": "ocr",
            "bbox": bbox,
            "center": _center_from_bbox(bbox),
            "confidence": confidence,
        })

    return candidates


def propose_targets(query: str, limit: int = 8) -> dict:
    """Return ranked target candidates from merged perception sources."""
    sources: List[str] = []
    candidates: List[Dict[str, Any]] = []

    frontmost_ax = _collect_frontmost_ax_targets()
    if frontmost_ax:
        sources.append("ax_frontmost")
        candidates.extend(frontmost_ax)

    dock_ax = _collect_dock_ax_targets()
    if dock_ax:
        sources.append("ax_dock")
        candidates.extend(dock_ax)

    ocr_targets = _collect_ocr_targets()
    if ocr_targets:
        sources.append("ocr")
        candidates.extend(ocr_targets)

    if not candidates:
        return {
            "ok": False,
            "error": (
                "No targets found. Accessibility may be denied, OCR may be unavailable, "
                "or nothing matched on screen."
            ),
        }

    scored = []
    for candidate in candidates:
        candidate_copy = dict(candidate)
        candidate_copy["score"] = _score_candidate(query, candidate_copy)
        scored.append(candidate_copy)

    ranked = sorted(scored, key=lambda item: item["score"], reverse=True)
    cached = _cache_targets(ranked[: max(1, limit)])
    return {
        "ok": True,
        "query": query,
        "sources": sources,
        "targets": cached,
    }


def click_target(target_id: str, button: str = "left", click_count: int = 1) -> dict:
    """Click the center of a previously proposed target."""
    _cleanup_cache()
    target = _TARGET_CACHE.get(target_id)
    if not target:
        return {"ok": False, "error": f"Unknown or expired target_id '{target_id}'"}

    center = target.get("center") or {}
    x = center.get("x")
    y = center.get("y")
    if x is None or y is None:
        return {"ok": False, "error": f"Target '{target_id}' does not have clickable coordinates"}

    if click_count == 2:
        result = double_click(int(x), int(y))
    else:
        result = click(int(x), int(y), button=button)

    if not result.get("ok"):
        return result

    return {
        "ok": True,
        "target_id": target_id,
        "label": target.get("label"),
        "source": target.get("source"),
        "x": int(x),
        "y": int(y),
        "click_count": click_count,
        "button": button,
    }
