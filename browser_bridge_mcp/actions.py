"""Shared browser actions used by the MCP runtime."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .browser import BridgeBrowser


DEFAULT_ACTION_WAIT_SECONDS = 1.2
DEFAULT_ACTION_LIMIT = 40
MAX_ACTION_LIMIT = 300
DEFAULT_EVENT_LIMIT = 120
MAX_EVENT_LIMIT = 500
DEFAULT_HTML_LIMIT = 200_000


_OBSERVER_SCRIPT = r"""
(() => {
  if (window.__bbmcpObserversInstalled) return;
  window.__bbmcpObserversInstalled = true;
  window.__bbmcpConsoleLogs = window.__bbmcpConsoleLogs || [];
  window.__bbmcpNetworkLogs = window.__bbmcpNetworkLogs || [];
  const MAX_BUFFER = 500;

  const pushBounded = (arr, value) => {
    arr.push(value);
    if (arr.length > MAX_BUFFER) {
      arr.splice(0, arr.length - MAX_BUFFER);
    }
  };

  const safeString = (value) => {
    try {
      if (value === undefined) return "undefined";
      if (value === null) return "null";
      if (typeof value === "string") return value.slice(0, 600);
      if (value instanceof Error) return `${value.name}: ${value.message}`.slice(0, 600);
      return JSON.stringify(value).slice(0, 600);
    } catch {
      try {
        return String(value).slice(0, 600);
      } catch {
        return "[unserializable]";
      }
    }
  };

  const now = () => new Date().toISOString();

  for (const level of ["log", "info", "warn", "error", "debug"]) {
    const original = console[level];
    if (typeof original !== "function") continue;
    if (original.__bbmcpWrapped) continue;

    const wrapped = function (...args) {
      try {
        pushBounded(window.__bbmcpConsoleLogs, {
          ts: now(),
          level,
          args: args.map(safeString),
        });
      } catch {}
      return original.apply(this, args);
    };
    wrapped.__bbmcpWrapped = true;
    console[level] = wrapped;
  }

  if (typeof window.fetch === "function" && !window.fetch.__bbmcpWrapped) {
    const originalFetch = window.fetch;
    const wrappedFetch = async (...args) => {
      const startedAt = Date.now();
      let url = "unknown";
      let method = "GET";
      try {
        const input = args[0];
        const init = args[1] || {};
        if (typeof input === "string") url = input;
        else if (input && typeof input.url === "string") url = input.url;
        if (init && init.method) method = String(init.method).toUpperCase();
      } catch {}

      try {
        const response = await originalFetch(...args);
        pushBounded(window.__bbmcpNetworkLogs, {
          ts: now(),
          type: "fetch",
          url: safeString(url),
          method,
          status: Number(response.status) || 0,
          ok: Boolean(response.ok),
          duration_ms: Date.now() - startedAt,
        });
        return response;
      } catch (error) {
        pushBounded(window.__bbmcpNetworkLogs, {
          ts: now(),
          type: "fetch",
          url: safeString(url),
          method,
          status: 0,
          ok: false,
          duration_ms: Date.now() - startedAt,
          error: safeString(error),
        });
        throw error;
      }
    };
    wrappedFetch.__bbmcpWrapped = true;
    window.fetch = wrappedFetch;
  }

  if (!XMLHttpRequest.prototype.__bbmcpWrapped) {
    const originalOpen = XMLHttpRequest.prototype.open;
    const originalSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (method, url, ...rest) {
      this.__bbmcpMeta = {
        method: method ? String(method).toUpperCase() : "GET",
        url: safeString(url),
      };
      return originalOpen.call(this, method, url, ...rest);
    };

    XMLHttpRequest.prototype.send = function (...args) {
      const startedAt = Date.now();
      const meta = this.__bbmcpMeta || { method: "GET", url: "unknown" };

      const onDone = () => {
        try {
          pushBounded(window.__bbmcpNetworkLogs, {
            ts: now(),
            type: "xhr",
            url: meta.url,
            method: meta.method,
            status: Number(this.status) || 0,
            ok: this.status >= 200 && this.status < 400,
            duration_ms: Date.now() - startedAt,
          });
        } catch {}
      };

      this.addEventListener("loadend", onDone, { once: true });
      return originalSend.apply(this, args);
    };
    XMLHttpRequest.prototype.__bbmcpWrapped = true;
  }
})();
"""


def clamp_limit(value: int, *, max_limit: int = MAX_ACTION_LIMIT) -> int:
    if value < 1:
        return 1
    if value > max_limit:
        return max_limit
    return value


def _looks_like_object_pairs(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            return False
        if not isinstance(item[0], str):
            return False
    return True


def normalize_evaluate_payload(value: Any) -> Any:
    """Normalize nodriver serialized Runtime values into plain Python."""
    if isinstance(value, dict) and "type" in value:
        kind = value.get("type")
        if kind == "null":
            return None
        if kind in {"string", "number", "boolean"}:
            return value.get("value")
        if kind == "array":
            raw_items = value.get("value", [])
            if isinstance(raw_items, list):
                return [normalize_evaluate_payload(item) for item in raw_items]
            return []
        if kind == "object":
            raw_obj = value.get("value", [])
            if _looks_like_object_pairs(raw_obj):
                return {item[0]: normalize_evaluate_payload(item[1]) for item in raw_obj}
            return raw_obj
        if "value" in value:
            return normalize_evaluate_payload(value["value"])
        return value

    if _looks_like_object_pairs(value):
        return {item[0]: normalize_evaluate_payload(item[1]) for item in value}

    if isinstance(value, list):
        return [normalize_evaluate_payload(item) for item in value]

    return value


def _snapshot_script(limit: int) -> str:
    return f"""
    (() => {{
      const clean = (value, maxLen = 160) => {{
        if (!value) return "";
        return String(value).replace(/\\s+/g, " ").trim().slice(0, maxLen);
      }};
      const selectors =
        'input,button,a,textarea,select,[role="button"],[role="textbox"],[contenteditable="true"]';
      const nodes = Array.from(document.querySelectorAll(selectors));
      const items = nodes.slice(0, {limit}).map((el, idx) => {{
        const attrs = {{}};
        for (const attr of ["id", "name", "type", "role", "aria-label", "placeholder", "href"]) {{
          const value = el.getAttribute(attr);
          if (value) attrs[attr] = clean(value);
        }}
        const hints = [];
        if (el.id) hints.push(`#${{el.id}}`);
        if (attrs["name"]) hints.push(`${{el.tagName.toLowerCase()}}[name="${{attrs["name"]}}"]`);
        if (attrs["aria-label"]) {{
          hints.push(`${{el.tagName.toLowerCase()}}[aria-label="${{attrs["aria-label"]}}"]`);
        }}
        if (!hints.length) hints.push(el.tagName.toLowerCase());
        return {{
          index: idx,
          tag: el.tagName.toLowerCase(),
          text: clean(el.innerText || el.textContent || ""),
          classes: clean(el.className || "", 120),
          attrs,
          locator_hints: hints.slice(0, 3),
        }};
      }});
      return {{
        url: location.href,
        title: document.title,
        total_interactive: nodes.length,
        returned: items.length,
        interactive: items,
      }};
    }})()
    """


def _query_script(selector: str, limit: int) -> str:
    selector_json = json.dumps(selector)
    return f"""
    (() => {{
      const selector = {selector_json};
      const clean = (value, maxLen = 160) => {{
        if (!value) return "";
        return String(value).replace(/\\s+/g, " ").trim().slice(0, maxLen);
      }};
      const nodes = Array.from(document.querySelectorAll(selector)).slice(0, {limit});
      const elements = nodes.map((el, idx) => {{
        const attrs = {{}};
        for (const attr of ["id", "name", "type", "role", "aria-label", "placeholder", "href"]) {{
          const value = el.getAttribute(attr);
          if (value) attrs[attr] = clean(value);
        }}
        return {{
          index: idx,
          tag: el.tagName.toLowerCase(),
          text: clean(el.innerText || el.textContent || ""),
          classes: clean(el.className || "", 120),
          attrs,
        }};
      }});
      return {{
        selector,
        count: elements.length,
        elements,
      }};
    }})()
    """


def _clear_selector_script(selector: str) -> str:
    selector_json = json.dumps(selector)
    return f"""
    (() => {{
      const el = document.querySelector({selector_json});
      if (!el) return false;
      if (!("value" in el)) return false;
      el.value = "";
      el.dispatchEvent(new Event("input", {{ bubbles: true }}));
      return true;
    }})()
    """


def _event_fetch_script(buffer_name: str, limit: int, clear: bool) -> str:
    clear_js = "true" if clear else "false"
    return f"""
    (() => {{
      const key = {json.dumps(buffer_name)};
      const source = Array.isArray(window[key]) ? window[key] : [];
      const rows = source.slice(-{limit});
      if ({clear_js} && Array.isArray(window[key])) {{
        window[key].length = 0;
      }}
      return {{
        returned: rows.length,
        total_available: source.length,
        rows,
      }};
    }})()
    """


async def ensure_observers(browser: BridgeBrowser) -> None:
    await browser.add_script_on_new_document(_OBSERVER_SCRIPT)
    await browser.evaluate(_OBSERVER_SCRIPT)


async def get_url_and_title(browser: BridgeBrowser) -> dict[str, Any]:
    title = await browser.evaluate("document.title")
    return {
        "url": str(browser.tab.url),
        "title": str(title) if title is not None else "",
    }


async def navigate_to(
    browser: BridgeBrowser,
    *,
    url: str,
    wait_seconds: float = DEFAULT_ACTION_WAIT_SECONDS,
) -> dict[str, Any]:
    await browser.goto(url, wait_seconds=max(0.0, wait_seconds))
    return await get_url_and_title(browser)


async def snapshot_interactive(browser: BridgeBrowser, *, limit: int) -> dict[str, Any]:
    payload = normalize_evaluate_payload(
        await browser.evaluate(_snapshot_script(clamp_limit(limit)))
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Snapshot action returned non-object payload.")
    return payload


async def query_selector(
    browser: BridgeBrowser,
    *,
    selector: str,
    limit: int,
) -> dict[str, Any]:
    payload = normalize_evaluate_payload(
        await browser.evaluate(_query_script(selector, clamp_limit(limit)))
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Query action returned non-object payload.")
    return payload


async def click_selector(
    browser: BridgeBrowser,
    *,
    selector: str,
    wait_seconds: float = DEFAULT_ACTION_WAIT_SECONDS,
) -> dict[str, Any]:
    element = await browser.select_first([selector])
    if not element:
        raise RuntimeError(f"No element found for selector: {selector}")
    try:
        await element.scroll_into_view()
    except Exception:
        pass
    await asyncio.sleep(0.2)
    await element.click()
    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)
    payload = await get_url_and_title(browser)
    payload["selector"] = selector
    return payload


async def type_into_selector(
    browser: BridgeBrowser,
    *,
    selector: str,
    text: str,
    clear: bool = False,
    submit: bool = False,
    wait_seconds: float = DEFAULT_ACTION_WAIT_SECONDS,
    key_delay_seconds: float = 0.015,
) -> dict[str, Any]:
    element = await browser.select_first([selector])
    if not element:
        raise RuntimeError(f"No element found for selector: {selector}")
    await element.click()
    await asyncio.sleep(0.2)
    if clear:
        await browser.evaluate(_clear_selector_script(selector))
        await asyncio.sleep(0.1)
    for char in text:
        await element.send_keys(char)
        if key_delay_seconds > 0:
            await asyncio.sleep(key_delay_seconds)
    if submit:
        await browser.press_key("Enter", "Enter", 13)
    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)
    payload = await get_url_and_title(browser)
    payload.update(
        {
            "selector": selector,
            "submitted": submit,
            "typed_chars": len(text),
        }
    )
    return payload


async def scroll_page(
    browser: BridgeBrowser,
    *,
    selector: str | None = None,
    delta_y: int = 1200,
    to_top: bool = False,
    to_bottom: bool = False,
    wait_seconds: float = DEFAULT_ACTION_WAIT_SECONDS,
) -> dict[str, Any]:
    if selector:
        element = await browser.select_first([selector])
        if not element:
            raise RuntimeError(f"No element found for selector: {selector}")
        await element.scroll_into_view()
        mode = "selector"
    elif to_top:
        await browser.evaluate("window.scrollTo(0, 0)")
        mode = "top"
    elif to_bottom:
        await browser.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        mode = "bottom"
    else:
        await browser.evaluate(f"window.scrollBy(0, {int(delta_y)})")
        mode = "delta"

    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)
    payload = await get_url_and_title(browser)
    payload.update(
        {
            "mode": mode,
            "selector": selector,
            "delta_y": int(delta_y),
        }
    )
    return payload


async def wait_seconds(seconds: float) -> dict[str, Any]:
    await asyncio.sleep(max(0.0, seconds))
    return {"seconds": max(0.0, seconds)}


async def wait_for_selector(
    browser: BridgeBrowser,
    *,
    selector: str,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    found = False
    error: str | None = None
    try:
        await browser.tab.wait_for(selector=selector, timeout=max(0.1, timeout_seconds))
        found = True
    except Exception as exc:
        error = str(exc)

    payload = await get_url_and_title(browser)
    payload.update(
        {
            "selector": selector,
            "found": found,
            "timeout_seconds": timeout_seconds,
        }
    )
    if error and not found:
        payload["error"] = error
    return payload


async def get_page_html(
    browser: BridgeBrowser,
    *,
    max_chars: int = DEFAULT_HTML_LIMIT,
) -> dict[str, Any]:
    html = str(await browser.tab.get_content())
    limit = max(1_000, int(max_chars))
    truncated = len(html) > limit
    return {
        "url": str(browser.tab.url),
        "html": html[:limit],
        "html_length": len(html),
        "truncated": truncated,
    }


async def get_console_messages(
    browser: BridgeBrowser,
    *,
    limit: int = DEFAULT_EVENT_LIMIT,
    clear: bool = False,
) -> dict[str, Any]:
    payload = normalize_evaluate_payload(
        await browser.evaluate(
            _event_fetch_script(
                "__bbmcpConsoleLogs",
                clamp_limit(limit, max_limit=MAX_EVENT_LIMIT),
                clear,
            )
        )
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Console event query returned non-object payload.")
    payload["rows"] = payload.get("rows", [])
    return payload


async def get_network_requests(
    browser: BridgeBrowser,
    *,
    limit: int = DEFAULT_EVENT_LIMIT,
    clear: bool = False,
) -> dict[str, Any]:
    payload = normalize_evaluate_payload(
        await browser.evaluate(
            _event_fetch_script(
                "__bbmcpNetworkLogs",
                clamp_limit(limit, max_limit=MAX_EVENT_LIMIT),
                clear,
            )
        )
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Network event query returned non-object payload.")
    payload["rows"] = payload.get("rows", [])
    return payload


async def take_screenshot(
    browser: BridgeBrowser,
    *,
    output_path: str,
    full_page: bool = False,
    image_format: str = "png",
) -> dict[str, Any]:
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    saved = await browser.tab.save_screenshot(
        filename=str(path),
        format=image_format,
        full_page=full_page,
    )
    return {
        "url": str(browser.tab.url),
        "path": str(saved),
        "full_page": full_page,
        "format": image_format,
    }
