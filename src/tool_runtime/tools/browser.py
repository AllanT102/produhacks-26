"""Chrome DOM interaction tools via Apple Events."""

from __future__ import annotations

import json
import subprocess
from typing import Any, Dict


def _run_osascript(script: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        return False, str(exc)

    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        return False, message or "osascript failed"
    return True, result.stdout.strip()


def _chrome_error(message: str) -> dict:
    if "Allow JavaScript from Apple Events" in message:
        return {
            "ok": False,
            "error": (
                "Chrome is blocking JavaScript from Apple Events. Enable "
                "View > Developer > Allow JavaScript from Apple Events."
            ),
        }
    return {"ok": False, "error": message}


def _execute_chrome_javascript(js: str) -> tuple[bool, str]:
    script = (
        'tell application "Google Chrome" to execute active tab of front window javascript '
        + json.dumps(js)
    )
    ok, output = _run_osascript(script)
    return ok, output


def _json_tool_output(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"))


def browser_query(query: str, limit: int = 8) -> dict:
    """Find semantic DOM targets in the active Chrome tab."""
    js = f"""
(() => {{
  const query = {json.dumps(query)};
  const limit = {int(limit)};
  const q = query.toLowerCase().trim();
  const qTokens = q.split(/\\s+/).filter(Boolean);

  const isVisible = (el) => {{
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  }};

  const labelFor = (el) => {{
    return [
      el.innerText,
      el.getAttribute('aria-label'),
      el.getAttribute('title'),
      el.getAttribute('placeholder'),
      el.value,
      el.textContent,
    ].filter(Boolean).map(s => s.trim()).find(Boolean) || '';
  }};

  const score = (label) => {{
    const hay = label.toLowerCase();
    let total = 0;
    if (!hay) return total;
    if (hay.includes(q)) total += 20;
    for (const token of qTokens) {{
      if (hay.includes(token)) total += 5;
    }}
    return total;
  }};

  const roleBoost = (role, label) => {{
    const lowerRole = (role || '').toLowerCase();
    const lowerLabel = (label || '').toLowerCase();
    let total = 0;
    if (q.includes('search')) {{
      if (lowerRole.includes('combobox') || lowerRole.includes('input') || lowerRole.includes('searchbox') || lowerRole === 'input') total += 12;
      if (lowerLabel === 'search' || lowerLabel.includes('search')) total += 4;
    }}
    if (q.includes('input') || q.includes('field') || q.includes('box')) {{
      if (lowerRole.includes('combobox') || lowerRole.includes('input') || lowerRole.includes('textarea')) total += 12;
    }}
    if (q.includes('button') || q.includes('subscribe')) {{
      if (lowerRole.includes('button')) total += 12;
    }}
    if (q.includes('link') || q.includes('result') || q.includes('channel')) {{
      if (lowerRole === 'a' || lowerRole.includes('link')) total += 10;
    }}
    return total;
  }};

  const makeRef = (index) => `codex-ref-${{Date.now()}}-${{index}}`;
  const seen = new Set();
  const candidates = [];
  const selector = [
    'button',
    'a',
    'input',
    'textarea',
    '[role="button"]',
    '[role="link"]',
    '[tabindex]',
    'yt-button-shape button',
    'ytd-button-renderer button',
    'tp-yt-paper-button',
  ].join(',');

  for (const el of Array.from(document.querySelectorAll(selector))) {{
    if (!isVisible(el)) continue;
    const rect = el.getBoundingClientRect();
    const label = labelFor(el);
    const role = el.getAttribute('role') || el.tagName.toLowerCase();
    const candidateScore = score(label + ' ' + role) + roleBoost(role, label);
    if (candidateScore <= 0) continue;

    const fingerprint = `${{label}}|${{role}}|${{Math.round(rect.left)}}|${{Math.round(rect.top)}}`;
    if (seen.has(fingerprint)) continue;
    seen.add(fingerprint);

    let ref = el.getAttribute('data-codex-ref');
    if (!ref) {{
      ref = makeRef(candidates.length);
      el.setAttribute('data-codex-ref', ref);
    }}

    candidates.push({{
      ref,
      label,
      role,
      bbox: {{
        x: Math.round(rect.left),
        y: Math.round(rect.top),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      }},
      center: {{
        x: Math.round(rect.left + rect.width / 2),
        y: Math.round(rect.top + rect.height / 2),
      }},
      score: candidateScore,
    }});
  }}

  candidates.sort((a, b) => b.score - a.score);
  return JSON.stringify({{
    ok: true,
    url: window.location.href,
    title: document.title,
    matches: candidates.slice(0, limit)
  }});
}})()
"""
    ok, output = _execute_chrome_javascript(js)
    if not ok:
        return _chrome_error(output)
    try:
        payload = json.loads(output)
    except Exception:
        return {"ok": False, "error": f"Chrome returned non-JSON output: {output[:200]}"}
    payload["ok"] = True
    return payload


def browser_click_ref(ref: str) -> dict:
    """Click an element previously identified by browser_query."""
    js = f"""
(() => {{
  const ref = {json.dumps(ref)};
  const el = document.querySelector(`[data-codex-ref="${{ref}}"]`);
  if (!el) return JSON.stringify({{ok: false, error: 'Element ref not found'}});
  el.scrollIntoView({{block: 'center', inline: 'center'}});
  el.click();
  const rect = el.getBoundingClientRect();
  return JSON.stringify({{
    ok: true,
    ref,
    label: (el.innerText || el.getAttribute('aria-label') || el.textContent || '').trim(),
    bbox: {{
      x: Math.round(rect.left),
      y: Math.round(rect.top),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
    }}
  }});
}})()
"""
    ok, output = _execute_chrome_javascript(js)
    if not ok:
        return _chrome_error(output)
    try:
        return json.loads(output)
    except Exception:
        return {"ok": False, "error": f"Chrome returned non-JSON output: {output[:200]}"}


def browser_scroll_to_text(text: str) -> dict:
    """Scroll the active Chrome tab until a visible text match is centered."""
    js = f"""
(() => {{
  const query = {json.dumps(text)};
  const q = query.toLowerCase().trim();
  const qTokens = q.split(/\\s+/).filter(Boolean);

  const tokenMatch = (hay, token) => {{
    if (!hay || !token) return false;
    if (/^[a-z0-9]{{1,2}}$/i.test(token)) {{
      const escaped = token.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
      return new RegExp(`(^|\\\\b)${{escaped}}(\\\\b|$)`, 'i').test(hay);
    }}
    return hay.includes(token);
  }};

  const isVisible = (el) => {{
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  }};

  const labelFor = (el) => {{
    return [
      el.innerText,
      el.getAttribute('aria-label'),
      el.getAttribute('title'),
      el.textContent,
    ].filter(Boolean).map(s => s.trim()).find(Boolean) || '';
  }};

  const score = (label, tagName) => {{
    const hay = (label || '').toLowerCase();
    const tag = (tagName || '').toLowerCase();
    let total = 0;
    if (!hay) return total;
    const matchedTokens = qTokens.filter((token) => tokenMatch(hay, token));
    if (!hay.includes(q)) {{
      if (qTokens.length >= 2 && matchedTokens.length < qTokens.length) return 0;
      if (qTokens.length === 1 && matchedTokens.length === 0) return 0;
    }}
    if (hay === q) total += 60;
    if (hay.includes(q)) total += 35;
    for (const token of qTokens) {{
      if (tokenMatch(hay, token)) total += 8;
    }}
    if (/^h[1-6]$/.test(tag)) total += 8;
    if (tag === 'li') total += 6;
    if (tag === 'summary' || tag === 'label') total += 5;
    const lengthPenalty = Math.max(0, Math.floor(hay.length / 120));
    return total - lengthPenalty;
  }};

  const selector = [
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'li', 'p', 'span', 'a', 'button', 'label',
    'summary', 'dt', 'dd', 'code', 'pre',
    '[role=\"heading\"]', '[role=\"button\"]', '[role=\"link\"]'
  ].join(',');

  const seen = new Set();
  const matches = [];

  for (const el of Array.from(document.querySelectorAll(selector))) {{
    if (!isVisible(el)) continue;
    const label = labelFor(el);
    const candidateScore = score(label, el.tagName);
    if (candidateScore <= 0) continue;
    const rect = el.getBoundingClientRect();
    const fingerprint = `${{label}}|${{el.tagName}}|${{Math.round(rect.left)}}|${{Math.round(rect.top)}}`;
    if (seen.has(fingerprint)) continue;
    seen.add(fingerprint);
    matches.push({{
      label,
      tag: el.tagName.toLowerCase(),
      score: candidateScore,
      bbox: {{
        x: Math.round(rect.left),
        y: Math.round(rect.top),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      }},
    }});
  }}

  matches.sort((a, b) => b.score - a.score);
  const best = matches[0];
  if (!best) return JSON.stringify({{ok: false, error: `No visible text match found for "${{query}}"`}});

  const target = Array.from(document.querySelectorAll(selector)).find((el) => {{
    if (!isVisible(el)) return false;
    const rect = el.getBoundingClientRect();
    const label = labelFor(el);
    return (
      label === best.label &&
      Math.round(rect.left) === best.bbox.x &&
      Math.round(rect.top) === best.bbox.y
    );
  }});

  if (!target) return JSON.stringify({{ok: false, error: 'Matched element disappeared before scrolling'}});
  target.scrollIntoView({{block: 'center', inline: 'nearest', behavior: 'instant'}});
  const finalRect = target.getBoundingClientRect();
  return JSON.stringify({{
    ok: true,
    text: query,
    label: labelFor(target),
    tag: target.tagName.toLowerCase(),
    bbox: {{
      x: Math.round(finalRect.left),
      y: Math.round(finalRect.top),
      width: Math.round(finalRect.width),
      height: Math.round(finalRect.height),
    }},
    url: window.location.href,
    title: document.title,
  }});
}})()
"""
    ok, output = _execute_chrome_javascript(js)
    if not ok:
        return _chrome_error(output)
    try:
        return json.loads(output)
    except Exception:
        return {"ok": False, "error": f"Chrome returned non-JSON output: {output[:200]}"}


def browser_fill_ref(ref: str, text: str, submit: bool = False) -> dict:
    """Fill an input-like element previously identified by browser_query."""
    js = f"""
(() => {{
  const ref = {json.dumps(ref)};
  const text = {json.dumps(text)};
  const submit = {str(bool(submit)).lower()};
  const el = document.querySelector(`[data-codex-ref="${{ref}}"]`);
  if (!el) return JSON.stringify({{ok: false, error: 'Element ref not found'}});
  el.focus();
  if ('value' in el) {{
    el.value = text;
  }} else {{
    el.textContent = text;
  }}
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  if (submit) {{
    el.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', bubbles: true }}));
    el.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', code: 'Enter', bubbles: true }}));
    if (el.form) el.form.submit();
  }}
  return JSON.stringify({{
    ok: true,
    ref,
    text,
    submit
  }});
}})()
"""
    ok, output = _execute_chrome_javascript(js)
    if not ok:
        return _chrome_error(output)
    try:
        return json.loads(output)
    except Exception:
        return {"ok": False, "error": f"Chrome returned non-JSON output: {output[:200]}"}


def browser_get_page() -> dict:
    """Return the current URL and title of the active Chrome tab."""
    url_ok, url = _run_osascript('tell application "Google Chrome" to get URL of active tab of front window')
    title_ok, title = _run_osascript('tell application "Google Chrome" to get title of active tab of front window')
    if not url_ok:
        return {"ok": False, "error": url}
    if not title_ok:
        return {"ok": False, "error": title}
    return {"ok": True, "url": url, "title": title}
