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


def browser_extract_text(
    scope: str = "page",
    fallback_scope: str = "",
    max_blocks: int = 5,
    max_chars: int = 1100,
) -> dict:
    """Extract readable text from the active Chrome tab for read-aloud flows."""
    js = f"""
(() => {{
  const requestedScope = {json.dumps(scope)};
  const fallbackScope = {json.dumps(fallback_scope)};
  const maxBlocks = Math.max(1, Number({int(max_blocks)}));
  const maxChars = Math.max(120, Number({int(max_chars)}));
  const blockSelector = 'h1,h2,h3,h4,p,li,blockquote,pre,figcaption,dd';
  const granularSelector = 'h1,h2,h3,h4,p,li,blockquote,figcaption,pre,div,span';

  const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  const isVisible = (el) => {{
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return (
      rect.width > 0 &&
      rect.height > 0 &&
      style.visibility !== 'hidden' &&
      style.display !== 'none' &&
      style.opacity !== '0'
    );
  }};
  const isBlocked = (el) => !!el.closest('nav,aside,form,menu,dialog,button,input,textarea,select,script,style,noscript');
  const intersectsViewport = (el) => {{
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    return rect.bottom > 0 && rect.top < window.innerHeight && rect.right > 0 && rect.left < window.innerWidth;
  }};
  const uiNoiseExact = new Set([
    'like',
    'comment',
    'repost',
    'send',
    'share',
    'follow',
    'connect',
    'message',
    'save',
    'dismiss',
    'report',
    'copy link',
    'see more',
    'show more',
    'read more',
    'learn more',
    'open',
    'close',
    'next',
    'previous',
    'home',
    'my network',
    'jobs',
    'messaging',
    'notifications',
    'me',
  ]);
  const isNoiseLine = (line) => {{
    const normalized = clean(line);
    if (!normalized) return true;
    const lower = normalized.toLowerCase();
    if (uiNoiseExact.has(lower)) return true;
    if (/^\\(?tv static\\)?$/i.test(lower)) return true;
    if (/^[\\d,.]+$/.test(lower)) return true;
    if (/^\\d+[smhdw]$/i.test(lower)) return true;
    if (/^[\\d,.]+\\s+(?:likes?|comments?|reposts?|followers?|connections?|views?)$/i.test(lower)) return true;
    if (/^(?:follow|connect|message)\\s+[a-z0-9 .'-]+$/i.test(lower) && normalized.length < 32) return true;
    return false;
  }};
  const uniqueLines = (lines) => {{
    const seen = new Set();
    const result = [];
    for (const line of lines) {{
      const normalized = clean(line);
      if (!normalized) continue;
      const key = normalized.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      result.push(normalized);
    }}
    return result;
  }};
  const collectReadableLines = (container) => {{
    if (!container) return [];
    const lines = [];
    for (const el of Array.from(container.querySelectorAll(granularSelector))) {{
      if (!isVisible(el) || isBlocked(el)) continue;
      const tag = el.tagName.toLowerCase();
      const raw = clean(el.innerText || el.textContent);
      if (!raw) continue;
      const parts = raw.split(/\\n+/).map(clean).filter(Boolean);
      const candidates = parts.length ? parts : [raw];
      for (const part of candidates) {{
        if (!part || isNoiseLine(part)) continue;
        if (!/^h[1-4]$/.test(tag) && part.length < 18) continue;
        lines.push(part);
      }}
      if (lines.length >= maxBlocks * 6) break;
    }}
    if (!lines.length) {{
      return uniqueLines(
        clean(container.innerText || container.textContent)
          .split(/\\n+/)
          .map(clean)
          .filter((line) => line && !isNoiseLine(line))
      );
    }}
    return uniqueLines(lines);
  }};
  const truncateText = (value) => {{
    const normalized = clean(value);
    if (normalized.length <= maxChars) return {{ text: normalized, truncated: false }};
    const sliced = normalized.slice(0, maxChars);
    const candidates = [
      sliced.lastIndexOf('. '),
      sliced.lastIndexOf('? '),
      sliced.lastIndexOf('! '),
      sliced.lastIndexOf('; '),
    ];
    const boundary = Math.max(...candidates);
    const cut = boundary >= Math.floor(maxChars * 0.55) ? boundary + 1 : maxChars;
    return {{ text: clean(sliced.slice(0, cut)), truncated: true }};
  }};
  const buildFocusText = () => {{
    const viewportCenterY = window.innerHeight / 2;
    const selectors = [
      'article',
      '[role="article"]',
      '[data-urn*="activity"]',
      '[data-id*="urn:li:activity"]',
      '.feed-shared-update-v2',
      '.update-components-update-v2',
      'main article',
      '.scaffold-layout__main',
      'main',
      '[role="main"]',
    ].join(',');
    const candidates = [];
    for (const el of Array.from(document.querySelectorAll(selectors))) {{
      if (!isVisible(el) || isBlocked(el) || !intersectsViewport(el)) continue;
      const rect = el.getBoundingClientRect();
      const lines = collectReadableLines(el);
      if (!lines.length) continue;
      const text = lines.join('\\n\\n');
      if (text.length < 80) continue;
      const tag = el.tagName.toLowerCase();
      const className = clean(el.className || '');
      const markerText = [
        className,
        el.getAttribute('data-urn') || '',
        el.getAttribute('data-id') || '',
        el.getAttribute('role') || '',
      ].join(' ').toLowerCase();
      let score = Math.min(text.length, 1400);
      if (tag === 'article') score += 240;
      if (markerText.includes('activity')) score += 360;
      if (/feed|update|story|article|post/.test(markerText)) score += 220;
      if (tag === 'main' || markerText.includes('main')) score -= 260;
      const centerY = rect.top + (rect.height / 2);
      score += Math.max(0, 320 - Math.abs(centerY - viewportCenterY));
      if (rect.height > window.innerHeight * 1.6) score -= 120;
      candidates.push({{ score, text }});
    }}
    candidates.sort((a, b) => b.score - a.score);
    return candidates.length ? candidates[0].text : '';
  }};
  const chooseRoot = () => {{
    const candidates = Array.from(
      document.querySelectorAll('article,main,[role="main"],[data-testid="article"],.article,.post,.content,#content')
    );
    candidates.push(document.body);
    let best = document.body;
    let bestScore = 0;
    for (const root of candidates) {{
      if (!root) continue;
      if (root !== document.body && !isVisible(root)) continue;
      const textLength = clean(root.innerText || root.textContent).length;
      const bonus = root.matches('article,main,[role="main"]') ? 600 : 0;
      const score = textLength + bonus;
      if (score > bestScore) {{
        best = root;
        bestScore = score;
      }}
    }}
    return best || document.body;
  }};

  const root = chooseRoot();
  const seen = new Set();
  const blocks = [];
  let gatheredChars = 0;

  for (const el of Array.from(root.querySelectorAll(blockSelector))) {{
    if (!isVisible(el) || isBlocked(el)) continue;
    const text = clean(el.innerText || el.textContent);
    if (!text) continue;
    const tag = el.tagName.toLowerCase();
    const minLength = /^h[1-3]$/.test(tag) ? 3 : (tag === 'li' ? 14 : 40);
    if (text.length < minLength) continue;
    const key = text.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    blocks.push({{ tag, text }});
    gatheredChars += text.length;
    if (blocks.length >= (maxBlocks * 3) || gatheredChars >= (maxChars * 2)) break;
  }}

  const selection = clean(window.getSelection ? window.getSelection().toString() : '');
  const headingEl = Array.from(root.querySelectorAll('h1,h2,h3,[role="heading"]')).find((el) => {{
    return isVisible(el) && clean(el.innerText || el.textContent).length >= 3;
  }});
  const headline = clean((headingEl && (headingEl.innerText || headingEl.textContent)) || document.title);
  const firstParagraph = (blocks.find((block) => block.tag === 'p') || blocks[0] || {{}}).text || '';
  const focusText = buildFocusText();
  const rootText = clean(root.innerText || root.textContent);
  let pageText = blocks.slice(0, maxBlocks).map((block) => block.text).join('\\n\\n');
  if ((!pageText || pageText.length < 120) && rootText) {{
    pageText = rootText;
  }}

  const resolveScope = (candidateScope) => {{
    switch (candidateScope) {{
      case 'selection':
        return selection;
      case 'headline':
        return headline;
      case 'first_paragraph':
        return firstParagraph;
      case 'focus':
        return focusText;
      default:
        return pageText;
    }}
  }};

  let usedScope = requestedScope || 'page';
  let chosenText = resolveScope(usedScope);
  if (!chosenText && fallbackScope) {{
    usedScope = fallbackScope;
    chosenText = resolveScope(usedScope);
  }}
  if (!chosenText && (requestedScope === 'page' || !requestedScope) && headline) {{
    usedScope = 'headline';
    chosenText = headline;
  }}

  if (!chosenText) {{
    return JSON.stringify({{
      ok: false,
      error: 'Could not find readable text on the active page.',
      requested_scope: requestedScope,
      fallback_scope: fallbackScope,
      title: document.title,
      url: window.location.href
    }});
  }}

  const truncated = truncateText(chosenText);
  return JSON.stringify({{
    ok: true,
    requested_scope: requestedScope,
    fallback_scope: fallbackScope,
    scope: usedScope,
    title: document.title,
    url: window.location.href,
    text: truncated.text,
    truncated: truncated.truncated,
    has_selection: Boolean(selection),
    preview: truncated.text.slice(0, 180),
    block_count: blocks.length,
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
