"""Session runtime for browser-bridge-mcp."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from . import actions as action_ops
from .actions import ensure_observers, get_url_and_title
from .browser import BridgeBrowser
from .cookies import load_cookie_file


READ_ONLY_BLOCKED_ACTIONS = {
    "browser_click",
    "browser_type",
    "browser_cookies_set",
    "browser_cookies_clear",
    "browser_set_file_input",
    "browser_storage_set",
    "browser_storage_clear",
    "browser_tab_new",
    "browser_tab_close",
}


def _default_policy() -> dict[str, Any]:
    return {
        "allowed_domains": None,
        "blocked_domains": [],
        "read_only": False,
        "allow_evaluate": True,
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_port(value: Any) -> int:
    try:
        port = int(value)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid port value: {value}") from exc
    if port <= 0 or port > 65535:
        raise ValueError(f"Port out of range: {port}")
    return port


def _connection_from_ws_url(ws_url: str) -> tuple[str, int]:
    parsed = urlparse(ws_url)
    if parsed.scheme not in {"ws", "wss", "http", "https"}:
        raise ValueError(f"Unsupported debugger URL scheme: {parsed.scheme}")
    if not parsed.hostname or not parsed.port:
        raise ValueError(f"Could not parse host/port from debugger URL: {ws_url}")
    return parsed.hostname, _normalize_port(parsed.port)


def _connection_from_state_file(state_file: str | Path) -> tuple[str, int]:
    path = Path(state_file).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"State file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    host = str(data.get("host", "")).strip()
    port = _normalize_port(data.get("port"))
    if not host:
        raise ValueError(f"State file {path} is missing host.")
    return host, port


def resolve_connection(
    *,
    host: str | None,
    port: int | None,
    ws_url: str | None,
    state_file: str | None,
) -> tuple[str, int]:
    provided = sum(
        [
            1 if (host is not None or port is not None) else 0,
            1 if ws_url else 0,
            1 if state_file else 0,
        ]
    )
    if provided == 0:
        raise ValueError("Provide host+port, ws_url, or state_file to attach.")
    if provided > 1:
        raise ValueError("Use exactly one connection mode: host+port OR ws_url OR state_file.")

    if ws_url:
        return _connection_from_ws_url(ws_url)

    if state_file:
        return _connection_from_state_file(state_file)

    if host is None or port is None:
        raise ValueError("Both host and port are required together.")
    return str(host).strip(), _normalize_port(port)


def _domain_from_value(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.hostname:
        return str(parsed.hostname).lower().strip(".")
    fallback = value.strip().lower()
    if "://" not in fallback:
        parsed_fallback = urlparse(f"https://{fallback}")
        if parsed_fallback.hostname:
            return str(parsed_fallback.hostname).lower().strip(".")
    return None


def _domain_matches(host: str, pattern: str) -> bool:
    normalized_host = host.lower().strip(".")
    normalized_pattern = pattern.lower().strip(".")
    return normalized_host == normalized_pattern or normalized_host.endswith(
        f".{normalized_pattern}"
    )


def _normalize_domains(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    normalized: list[str] = []
    for raw in value:
        domain = _domain_from_value(raw)
        if domain:
            normalized.append(domain)
    return sorted(set(normalized))


SENSITIVE_TRACE_KEYS = {
    "password",
    "token",
    "secret",
    "authorization",
    "cookie",
    "cookies",
}


def _sanitize_trace_value(value: Any, *, key_hint: str | None = None) -> Any:
    if key_hint:
        lowered = key_hint.lower()
        if lowered == "text" or any(secret in lowered for secret in SENSITIVE_TRACE_KEYS):
            return "***"

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_sanitize_trace_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _sanitize_trace_value(item, key_hint=str(key))
            for key, item in value.items()
        }
    return str(value)


@dataclass
class BrowserSession:
    session_id: str
    browser: BridgeBrowser
    mode: str
    created_at: str
    headless: bool
    connection_host: str | None
    connection_port: int | None
    websocket_url: str | None
    metadata: dict[str, Any]
    last_known_url: str | None = None
    last_known_title: str | None = None
    policy: dict[str, Any] = field(default_factory=_default_policy)
    trace_id: str | None = None
    trace_active: bool = False
    trace_started_at: str | None = None
    trace_stopped_at: str | None = None
    trace_capture_screenshot_on_error: bool = True
    trace_capture_html_on_error: bool = False
    trace_replay_active: bool = False
    trace_events: list[dict[str, Any]] = field(default_factory=list)
    action_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def summary(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "created_at": self.created_at,
            "headless": self.headless,
            "connection_host": self.connection_host,
            "connection_port": self.connection_port,
            "websocket_url": self.websocket_url,
            "last_known_url": self.last_known_url,
            "last_known_title": self.last_known_title,
            "metadata": self.metadata,
            "policy": self.policy,
            "trace_id": self.trace_id,
            "trace_active": self.trace_active,
            "trace_event_count": len(self.trace_events),
        }


class BrowserSessionManager:
    """Owns active browser sessions and serialized action execution."""

    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSession] = {}
        self._sessions_lock = asyncio.Lock()

    async def list_sessions(self) -> list[dict[str, Any]]:
        async with self._sessions_lock:
            sessions = list(self._sessions.values())
        return [session.summary() for session in sessions]

    async def _insert_session(self, session: BrowserSession) -> None:
        async with self._sessions_lock:
            if session.session_id in self._sessions:
                raise ValueError(f"Session id already exists: {session.session_id}")
            self._sessions[session.session_id] = session

    async def _pop_session(self, session_id: str) -> BrowserSession | None:
        async with self._sessions_lock:
            return self._sessions.pop(session_id, None)

    async def get_session(self, session_id: str) -> BrowserSession:
        async with self._sessions_lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        return session

    async def set_policy(
        self,
        *,
        session_id: str,
        allowed_domains: list[str] | None = None,
        blocked_domains: list[str] | None = None,
        read_only: bool | None = None,
        allow_evaluate: bool | None = None,
    ) -> dict[str, Any]:
        session = await self.get_session(session_id)
        policy = dict(_default_policy())
        policy.update(session.policy or {})
        if allowed_domains is not None:
            policy["allowed_domains"] = _normalize_domains(allowed_domains)
        if blocked_domains is not None:
            policy["blocked_domains"] = _normalize_domains(blocked_domains) or []
        if read_only is not None:
            policy["read_only"] = bool(read_only)
        if allow_evaluate is not None:
            policy["allow_evaluate"] = bool(allow_evaluate)
        session.policy = policy
        return {
            "session_id": session.session_id,
            "policy": policy,
        }

    async def get_policy(self, *, session_id: str) -> dict[str, Any]:
        session = await self.get_session(session_id)
        policy = dict(_default_policy())
        policy.update(session.policy or {})
        session.policy = policy
        return {
            "session_id": session.session_id,
            "policy": policy,
        }

    def _policy_denial(
        self,
        *,
        session: BrowserSession,
        action_name: str,
        action_args: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        policy = dict(_default_policy())
        policy.update(session.policy or {})

        if policy.get("read_only") and action_name in READ_ONLY_BLOCKED_ACTIONS:
            return {
                "allowed": False,
                "reason_code": "read_only_block",
                "reason": f"Action blocked by read_only policy: {action_name}",
            }

        if not policy.get("allow_evaluate", True) and action_name == "browser_evaluate":
            return {
                "allowed": False,
                "reason_code": "evaluate_blocked",
                "reason": "Action blocked because allow_evaluate is false.",
            }

        target_url: str | None = None
        if action_args and isinstance(action_args.get("url"), str):
            target_url = action_args["url"]
        elif isinstance(session.last_known_url, str):
            target_url = session.last_known_url

        domain = _domain_from_value(target_url)
        blocked_domains = policy.get("blocked_domains") or []
        if domain and any(_domain_matches(domain, blocked) for blocked in blocked_domains):
            return {
                "allowed": False,
                "reason_code": "domain_blocked",
                "reason": f"Action blocked by blocked_domains policy for domain: {domain}",
                "domain": domain,
            }

        allowed_domains = policy.get("allowed_domains")
        if domain and allowed_domains and not any(
            _domain_matches(domain, allowed) for allowed in allowed_domains
        ):
            return {
                "allowed": False,
                "reason_code": "domain_not_allowed",
                "reason": f"Action domain is not in allowed_domains: {domain}",
                "domain": domain,
            }
        return None

    async def start_trace(
        self,
        *,
        session_id: str,
        trace_id: str | None = None,
        capture_screenshot_on_error: bool = True,
        capture_html_on_error: bool = False,
    ) -> dict[str, Any]:
        session = await self.get_session(session_id)
        session.trace_id = trace_id or f"trace_{uuid.uuid4().hex[:12]}"
        session.trace_active = True
        session.trace_started_at = _utc_now_iso()
        session.trace_stopped_at = None
        session.trace_capture_screenshot_on_error = bool(capture_screenshot_on_error)
        session.trace_capture_html_on_error = bool(capture_html_on_error)
        session.trace_replay_active = False
        session.trace_events = []
        return {
            "session_id": session.session_id,
            "trace_id": session.trace_id,
            "started": True,
            "started_at": session.trace_started_at,
            "capture_screenshot_on_error": session.trace_capture_screenshot_on_error,
            "capture_html_on_error": session.trace_capture_html_on_error,
        }

    async def stop_trace(self, *, session_id: str) -> dict[str, Any]:
        session = await self.get_session(session_id)
        session.trace_active = False
        session.trace_stopped_at = _utc_now_iso()
        errors = sum(1 for event in session.trace_events if event.get("error"))
        return {
            "session_id": session.session_id,
            "trace_id": session.trace_id,
            "stopped": True,
            "started_at": session.trace_started_at,
            "stopped_at": session.trace_stopped_at,
            "steps": len(session.trace_events),
            "errors": errors,
        }

    async def get_trace_events(
        self,
        *,
        session_id: str,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        session = await self.get_session(session_id)
        normalized_offset = max(0, int(offset))
        normalized_limit = max(1, min(int(limit), 1000))
        events = session.trace_events[normalized_offset : normalized_offset + normalized_limit]
        return {
            "session_id": session.session_id,
            "trace_id": session.trace_id,
            "total_available": len(session.trace_events),
            "returned": len(events),
            "offset": normalized_offset,
            "limit": normalized_limit,
            "events": events,
        }

    async def export_trace(
        self,
        *,
        session_id: str,
        output_path: str,
    ) -> dict[str, Any]:
        session = await self.get_session(session_id)
        path = Path(output_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "trace_version": "1.0",
            "trace_id": session.trace_id,
            "session_id": session.session_id,
            "started_at": session.trace_started_at,
            "stopped_at": session.trace_stopped_at,
            "events": session.trace_events,
        }
        serialized = json.dumps(payload, ensure_ascii=True, indent=2)
        path.write_text(serialized, encoding="utf-8")
        checksum = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return {
            "session_id": session.session_id,
            "trace_id": session.trace_id,
            "path": str(path),
            "event_count": len(session.trace_events),
            "checksum": checksum,
        }

    def _build_replay_operation(
        self,
        *,
        action_name: str,
        inputs: dict[str, Any],
    ) -> Callable[[BridgeBrowser], Awaitable[Any]] | None:
        if action_name == "browser_url":
            return action_ops.get_url_and_title
        if action_name == "browser_navigate":
            url = inputs.get("url")
            if not isinstance(url, str):
                return None
            return lambda browser: action_ops.navigate_to(
                browser,
                url=url,
                wait_seconds=float(inputs.get("wait_seconds", action_ops.DEFAULT_ACTION_WAIT_SECONDS)),
            )
        if action_name == "browser_back":
            return lambda browser: action_ops.navigate_back(
                browser,
                wait_seconds=float(inputs.get("wait_seconds", action_ops.DEFAULT_ACTION_WAIT_SECONDS)),
            )
        if action_name == "browser_forward":
            return lambda browser: action_ops.navigate_forward(
                browser,
                wait_seconds=float(inputs.get("wait_seconds", action_ops.DEFAULT_ACTION_WAIT_SECONDS)),
            )
        if action_name == "browser_reload":
            return lambda browser: action_ops.reload_page(
                browser,
                wait_seconds=float(inputs.get("wait_seconds", action_ops.DEFAULT_ACTION_WAIT_SECONDS)),
                ignore_cache=bool(inputs.get("ignore_cache", False)),
            )
        if action_name == "browser_wait":
            return lambda _: action_ops.wait_seconds(
                float(inputs.get("seconds", action_ops.DEFAULT_ACTION_WAIT_SECONDS))
            )
        if action_name == "browser_wait_for_selector":
            selector = inputs.get("selector")
            if not isinstance(selector, str):
                return None
            return lambda browser: action_ops.wait_for_selector(
                browser,
                selector=selector,
                timeout_seconds=float(inputs.get("timeout_seconds", 10.0)),
            )
        if action_name == "browser_click":
            selector = inputs.get("selector")
            if not isinstance(selector, str):
                return None
            return lambda browser: action_ops.click_selector(
                browser,
                selector=selector,
                wait_seconds=float(inputs.get("wait_seconds", action_ops.DEFAULT_ACTION_WAIT_SECONDS)),
            )
        if action_name == "browser_type":
            selector = inputs.get("selector")
            text = inputs.get("text")
            if not isinstance(selector, str) or not isinstance(text, str):
                return None
            return lambda browser: action_ops.type_into_selector(
                browser,
                selector=selector,
                text=text,
                clear=bool(inputs.get("clear", False)),
                submit=bool(inputs.get("submit", False)),
                wait_seconds=float(inputs.get("wait_seconds", action_ops.DEFAULT_ACTION_WAIT_SECONDS)),
            )
        if action_name == "browser_scroll":
            return lambda browser: action_ops.scroll_page(
                browser,
                selector=inputs.get("selector"),
                delta_y=int(inputs.get("delta_y", 1200)),
                to_top=bool(inputs.get("to_top", False)),
                to_bottom=bool(inputs.get("to_bottom", False)),
                wait_seconds=float(inputs.get("wait_seconds", action_ops.DEFAULT_ACTION_WAIT_SECONDS)),
            )
        if action_name == "browser_snapshot":
            return lambda browser: action_ops.snapshot_interactive(
                browser,
                limit=int(inputs.get("limit", action_ops.DEFAULT_ACTION_LIMIT)),
            )
        if action_name == "browser_query":
            selector = inputs.get("selector")
            if not isinstance(selector, str):
                return None
            return lambda browser: action_ops.query_selector(
                browser,
                selector=selector,
                limit=int(inputs.get("limit", action_ops.DEFAULT_ACTION_LIMIT)),
            )
        if action_name == "browser_evaluate":
            script = inputs.get("script")
            if not isinstance(script, str):
                return None
            return lambda browser: browser.evaluate(script)
        return None

    async def replay_trace(
        self,
        *,
        trace_path: str,
        session_id: str | None = None,
        stop_on_error: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        path = Path(trace_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Trace file not found: {path}")

        payload = json.loads(path.read_text(encoding="utf-8"))
        events = payload.get("events", [])
        if not isinstance(events, list):
            raise ValueError("Invalid trace file: events must be a list.")

        resolved_session_id = session_id or str(payload.get("session_id") or "").strip()
        if not resolved_session_id:
            raise ValueError("Provide session_id or use a trace file with session_id.")

        session = await self.get_session(resolved_session_id)
        outcomes: list[dict[str, Any]] = []
        passed = 0
        failed = 0
        skipped = 0

        previous_replay_state = session.trace_replay_active
        session.trace_replay_active = True
        try:
            for index, event in enumerate(events):
                action_name = str(event.get("action") or "")
                inputs_raw = event.get("inputs", {})
                inputs = inputs_raw if isinstance(inputs_raw, dict) else {}
                operation = self._build_replay_operation(action_name=action_name, inputs=inputs)
                if operation is None:
                    skipped += 1
                    outcomes.append(
                        {
                            "index": index,
                            "action": action_name,
                            "status": "skipped",
                            "reason": "unsupported_action_or_missing_inputs",
                        }
                    )
                    if stop_on_error and not dry_run:
                        break
                    continue

                if dry_run:
                    passed += 1
                    outcomes.append(
                        {
                            "index": index,
                            "action": action_name,
                            "status": "dry_run_ok",
                        }
                    )
                    continue

                try:
                    result = await self.run_action(
                        session_id=resolved_session_id,
                        action_name=action_name,
                        action_args=inputs,
                        operation=operation,
                    )
                    if isinstance(result, dict) and result.get("allowed") is False:
                        failed += 1
                        outcomes.append(
                            {
                                "index": index,
                                "action": action_name,
                                "status": "failed",
                                "reason": result.get("reason") or "policy_denied",
                            }
                        )
                        if stop_on_error:
                            break
                    else:
                        passed += 1
                        outcomes.append(
                            {
                                "index": index,
                                "action": action_name,
                                "status": "passed",
                            }
                        )
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    outcomes.append(
                        {
                            "index": index,
                            "action": action_name,
                            "status": "failed",
                            "reason": str(exc),
                        }
                    )
                    if stop_on_error:
                        break
        finally:
            session.trace_replay_active = previous_replay_state

        return {
            "trace_path": str(path),
            "session_id": resolved_session_id,
            "dry_run": bool(dry_run),
            "stop_on_error": bool(stop_on_error),
            "total_events": len(events),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "outcomes": outcomes,
        }

    async def _capture_trace_artifacts(self, session: BrowserSession) -> dict[str, Any]:
        artifacts: dict[str, Any] = {}
        tab = getattr(session.browser, "tab", None)
        if not tab:
            return artifacts

        if session.trace_capture_screenshot_on_error:
            screenshot_path = (
                Path(tempfile.gettempdir())
                / f"bbmcp-trace-{session.trace_id or 'trace'}-{uuid.uuid4().hex[:8]}.png"
            )
            try:
                saved = await tab.save_screenshot(
                    filename=str(screenshot_path),
                    format="png",
                    full_page=False,
                )
                artifacts["screenshot_path"] = str(saved)
            except Exception:
                pass

        if session.trace_capture_html_on_error:
            html_path = (
                Path(tempfile.gettempdir())
                / f"bbmcp-trace-{session.trace_id or 'trace'}-{uuid.uuid4().hex[:8]}.html"
            )
            try:
                html = str(await tab.get_content())
                html_path.write_text(html, encoding="utf-8")
                artifacts["html_path"] = str(html_path)
            except Exception:
                pass
        return artifacts

    def _append_trace_event(
        self,
        *,
        session: BrowserSession,
        action_name: str,
        inputs: dict[str, Any] | None,
        result: Any,
        error: str | None,
        url_before: str | None,
        title_before: str | None,
        duration_ms: int,
        artifacts: dict[str, Any] | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "index": len(session.trace_events),
            "timestamp": _utc_now_iso(),
            "action": action_name,
            "inputs": _sanitize_trace_value(inputs or {}),
            "result": _sanitize_trace_value(result),
            "url_before": url_before,
            "url_after": session.last_known_url,
            "title_before": title_before,
            "title_after": session.last_known_title,
            "duration_ms": duration_ms,
        }
        if error:
            event["error"] = error
        if artifacts:
            event["artifacts"] = artifacts
        session.trace_events.append(event)
        if len(session.trace_events) > 5000:
            session.trace_events = session.trace_events[-5000:]
            for idx, row in enumerate(session.trace_events):
                row["index"] = idx

    async def start_session(
        self,
        *,
        session_id: str | None,
        headless: bool,
        start_url: str | None,
        user_data_dir: str | None,
        browser_args: list[str] | None,
        browser_executable_path: str | None,
        sandbox: bool,
        cookie_file: str | None,
        cookie_fallback_domain: str | None,
    ) -> dict[str, Any]:
        resolved_session_id = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        browser = BridgeBrowser(
            headless=headless,
            user_data_dir=user_data_dir,
            browser_args=browser_args,
            browser_executable_path=browser_executable_path,
            sandbox=sandbox,
        )
        await browser.start()
        try:
            if cookie_file:
                cookies = load_cookie_file(cookie_file)
                await browser.set_cookies(cookies, fallback_domain=cookie_fallback_domain)

            if start_url:
                await browser.goto(start_url, wait_seconds=1.2)

            await ensure_observers(browser)
            page = await get_url_and_title(browser)
            session = BrowserSession(
                session_id=resolved_session_id,
                browser=browser,
                mode="launch",
                created_at=_utc_now_iso(),
                headless=headless,
                connection_host=browser.connection_host,
                connection_port=browser.connection_port,
                websocket_url=browser.websocket_url,
                metadata={
                    "cookie_file": str(Path(cookie_file).expanduser()) if cookie_file else None,
                    "cookie_fallback_domain": cookie_fallback_domain,
                    "user_data_dir": user_data_dir,
                    "browser_args": list(browser_args or []),
                    "browser_executable_path": browser_executable_path,
                    "sandbox": sandbox,
                },
                last_known_url=page.get("url"),
                last_known_title=page.get("title"),
            )
            await self._insert_session(session)
            return session.summary()
        except Exception:
            await browser.close()
            raise

    async def attach_session(
        self,
        *,
        session_id: str | None,
        host: str | None,
        port: int | None,
        ws_url: str | None,
        state_file: str | None,
        start_url: str | None,
    ) -> dict[str, Any]:
        resolved_session_id = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        attach_host, attach_port = resolve_connection(
            host=host,
            port=port,
            ws_url=ws_url,
            state_file=state_file,
        )
        browser = BridgeBrowser(connect_host=attach_host, connect_port=attach_port)
        await browser.start()
        try:
            if start_url:
                await browser.goto(start_url, wait_seconds=1.2)
            await ensure_observers(browser)
            page = await get_url_and_title(browser)
            session = BrowserSession(
                session_id=resolved_session_id,
                browser=browser,
                mode="attach",
                created_at=_utc_now_iso(),
                headless=False,
                connection_host=browser.connection_host,
                connection_port=browser.connection_port,
                websocket_url=browser.websocket_url,
                metadata={
                    "ws_url": ws_url,
                    "state_file": str(Path(state_file).expanduser()) if state_file else None,
                },
                last_known_url=page.get("url"),
                last_known_title=page.get("title"),
            )
            await self._insert_session(session)
            return session.summary()
        except Exception:
            await browser.close()
            raise

    async def stop_session(self, *, session_id: str) -> dict[str, Any]:
        session = await self._pop_session(session_id)
        if session is None:
            return {
                "session_id": session_id,
                "stopped": False,
                "reason": "not_found",
            }
        await session.browser.close()
        return {
            "session_id": session_id,
            "stopped": True,
            "stopped_at": _utc_now_iso(),
        }

    async def stop_all_sessions(self) -> dict[str, Any]:
        async with self._sessions_lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        stopped_ids: list[str] = []
        for session in sessions:
            await session.browser.close()
            stopped_ids.append(session.session_id)
        return {
            "stopped_count": len(stopped_ids),
            "session_ids": stopped_ids,
        }

    async def run_action(
        self,
        *,
        session_id: str,
        action_name: str,
        operation: Callable[[BridgeBrowser], Awaitable[Any]],
        action_args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = await self.get_session(session_id)
        async with session.action_lock:
            loop = asyncio.get_running_loop()
            started_at = loop.time()
            url_before = session.last_known_url
            title_before = session.last_known_title
            denial = self._policy_denial(
                session=session,
                action_name=action_name,
                action_args=action_args,
            )
            if denial:
                response = {
                    "session_id": session.session_id,
                    "action": action_name,
                    "executed_at": _utc_now_iso(),
                    **denial,
                }
                if session.trace_active and not session.trace_replay_active:
                    duration_ms = int(max(0.0, (loop.time() - started_at) * 1000))
                    self._append_trace_event(
                        session=session,
                        action_name=action_name,
                        inputs=action_args,
                        result=response,
                        error=None,
                        url_before=url_before,
                        title_before=title_before,
                        duration_ms=duration_ms,
                    )
                return response

            try:
                payload = await operation(session.browser)
            except Exception as exc:
                if session.trace_active and not session.trace_replay_active:
                    artifacts = await self._capture_trace_artifacts(session)
                    duration_ms = int(max(0.0, (loop.time() - started_at) * 1000))
                    self._append_trace_event(
                        session=session,
                        action_name=action_name,
                        inputs=action_args,
                        result=None,
                        error=str(exc),
                        url_before=url_before,
                        title_before=title_before,
                        duration_ms=duration_ms,
                        artifacts=artifacts,
                    )
                raise

            if isinstance(payload, dict):
                if isinstance(payload.get("url"), str):
                    session.last_known_url = payload["url"]
                if isinstance(payload.get("title"), str):
                    session.last_known_title = payload["title"]

            response: dict[str, Any] = {
                "session_id": session.session_id,
                "action": action_name,
                "executed_at": _utc_now_iso(),
            }
            if isinstance(payload, dict):
                response.update(payload)
            else:
                response["payload"] = payload

            if session.trace_active and not session.trace_replay_active:
                duration_ms = int(max(0.0, (loop.time() - started_at) * 1000))
                trace_result = dict(response)
                trace_result.pop("session_id", None)
                trace_result.pop("action", None)
                trace_result.pop("executed_at", None)
                self._append_trace_event(
                    session=session,
                    action_name=action_name,
                    inputs=action_args,
                    result=trace_result,
                    error=None,
                    url_before=url_before,
                    title_before=title_before,
                    duration_ms=duration_ms,
                )
            return response
