"""Session runtime for browser-bridge-mcp."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from .actions import ensure_observers, get_url_and_title
from .browser import BridgeBrowser
from .cookies import load_cookie_file


READ_ONLY_BLOCKED_ACTIONS = {
    "browser_click",
    "browser_type",
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
            denial = self._policy_denial(
                session=session,
                action_name=action_name,
                action_args=action_args,
            )
            if denial:
                return {
                    "session_id": session.session_id,
                    "action": action_name,
                    "executed_at": _utc_now_iso(),
                    **denial,
                }
            payload = await operation(session.browser)
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
            return response
