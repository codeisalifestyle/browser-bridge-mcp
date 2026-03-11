"""Stealth browser helpers built on nodriver."""

from __future__ import annotations

import asyncio
import logging
from typing import Any


logger = logging.getLogger(__name__)


class BridgeBrowser:
    """Thin wrapper around nodriver with launch/attach support."""

    def __init__(
        self,
        *,
        headless: bool = False,
        connect_host: str | None = None,
        connect_port: int | None = None,
        user_data_dir: str | None = None,
        browser_args: list[str] | None = None,
        browser_executable_path: str | None = None,
        sandbox: bool = True,
    ):
        self.headless = headless
        self.connect_host = connect_host
        self.connect_port = connect_port
        self.user_data_dir = user_data_dir
        self.browser_args = list(browser_args or [])
        self.browser_executable_path = browser_executable_path
        self.sandbox = sandbox
        self.browser: Any = None
        self.tab: Any = None
        self._cdp_network: Any = None
        self._cdp_storage: Any = None
        self._cdp_input: Any = None
        self._cdp_page: Any = None
        self._owns_process: bool = False

    async def __aenter__(self) -> "BridgeBrowser":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def start(self) -> None:
        """Start a browser or attach to an existing debugger endpoint."""
        try:
            import nodriver as uc
            import nodriver.cdp.input_ as cdp_input
            import nodriver.cdp.network as cdp_network
            import nodriver.cdp.page as cdp_page
            import nodriver.cdp.storage as cdp_storage
        except ImportError as exc:
            raise RuntimeError("nodriver is required. Install dependencies first.") from exc
        except Exception as exc:
            raise RuntimeError(
                "Failed to import nodriver. If you are on Python 3.14, use Python 3.13 "
                "or lower for now due to an upstream nodriver compatibility issue."
            ) from exc

        self._cdp_network = cdp_network
        self._cdp_storage = cdp_storage
        self._cdp_input = cdp_input
        self._cdp_page = cdp_page

        attach_mode = self.connect_host is not None and self.connect_port is not None
        self._owns_process = not attach_mode

        if attach_mode:
            try:
                self.browser = await uc.start(host=self.connect_host, port=self.connect_port)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to connect to browser at {self.connect_host}:{self.connect_port}."
                ) from exc
        else:
            config_kwargs: dict[str, Any] = {
                "headless": self.headless,
                "sandbox": self.sandbox,
            }
            if self.user_data_dir:
                config_kwargs["user_data_dir"] = self.user_data_dir
            if self.browser_executable_path:
                config_kwargs["browser_executable_path"] = self.browser_executable_path

            merged_args: list[str] = list(self.browser_args)
            if self.headless:
                merged_args.append("--window-size=1920,1080")
            if merged_args:
                config_kwargs["browser_args"] = merged_args

            try:
                self.browser = await uc.start(**config_kwargs)
            except Exception as primary_exc:
                logger.warning(
                    "Primary browser startup failed (%s). Retrying with sandbox disabled.",
                    primary_exc,
                )
                try:
                    retry_kwargs = dict(config_kwargs)
                    if retry_kwargs.get("sandbox", True):
                        retry_kwargs["sandbox"] = False
                    self.browser = await uc.start(**retry_kwargs)
                except Exception as retry_exc:
                    raise RuntimeError(
                        "Failed to start browser. If you are on Python 3.14, use Python 3.13 "
                        "or lower for now due to an upstream nodriver compatibility issue."
                    ) from retry_exc
        self.tab = self.browser.main_tab
        await asyncio.sleep(1.2)

        if self._owns_process:
            await self._inject_stealth_script()
            if self.headless:
                await self._apply_headless_user_agent()

    async def close(self) -> None:
        if self.browser is None:
            return
        try:
            if self._owns_process:
                self.browser.stop()
        finally:
            self.browser = None
            self.tab = None
            self._owns_process = False

    async def _inject_stealth_script(self) -> None:
        script = """
            Object.defineProperty(navigator, 'webdriver', {
              get: () => undefined,
              configurable: true,
            });
            window.chrome = window.chrome || { runtime: {} };
        """
        await self.tab.send(self._cdp_page.add_script_to_evaluate_on_new_document(source=script))

    async def _apply_headless_user_agent(self) -> None:
        """Replace HeadlessChrome token in headless mode."""
        try:
            current_ua = await self.tab.evaluate("navigator.userAgent")
            if not isinstance(current_ua, str) or "HeadlessChrome" not in current_ua:
                return
            clean_ua = current_ua.replace("HeadlessChrome", "Chrome")
            await self.tab.send(self._cdp_network.set_user_agent_override(user_agent=clean_ua))
            logger.info("Applied headless-safe user agent override.")
        except Exception as exc:
            logger.warning("Could not override headless user-agent: %s", exc)

    async def add_script_on_new_document(self, source: str) -> None:
        await self.tab.send(self._cdp_page.add_script_to_evaluate_on_new_document(source=source))

    async def goto(self, url: str, *, wait_seconds: float = 0.0) -> None:
        await self.tab.get(url)
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)

    async def go_back(self) -> None:
        await self.evaluate("history.back()")

    async def go_forward(self) -> None:
        await self.evaluate("history.forward()")

    async def reload(self, *, ignore_cache: bool = False) -> None:
        if not self.tab:
            raise RuntimeError("Browser not started")

        current_url = str(getattr(self.tab, "url", "") or "")
        if ignore_cache and self._cdp_page is not None:
            try:
                await self.tab.send(self._cdp_page.reload(ignore_cache=True))
                return
            except Exception as exc:
                logger.debug("CDP cache-bypass reload failed, falling back: %s", exc)

        try:
            await self.evaluate("location.reload()")
        except Exception:
            if current_url:
                await self.goto(current_url)

    async def evaluate(self, script: str) -> Any:
        return await self.tab.evaluate(script)

    @staticmethod
    def _tab_id(tab: Any) -> str:
        target = getattr(tab, "target", None)
        target_id = getattr(target, "target_id", None)
        if target_id is None:
            return str(id(tab))
        return str(target_id)

    async def _page_tabs(self) -> list[Any]:
        if self.browser is None:
            raise RuntimeError("Browser not started")
        await self.browser.update_targets()
        tabs = list(getattr(self.browser, "tabs", []) or [])
        page_tabs: list[Any] = []
        for tab in tabs:
            target = getattr(tab, "target", None)
            tab_type = getattr(target, "type_", "page")
            if tab_type == "page":
                page_tabs.append(tab)
        if not page_tabs and self.tab is not None:
            return [self.tab]
        return page_tabs

    def _tab_summary(self, tab: Any, *, index: int, active_id: str | None) -> dict[str, Any]:
        target = getattr(tab, "target", None)
        tab_id = self._tab_id(tab)
        url = str(getattr(tab, "url", "") or getattr(target, "url", "") or "")
        title = str(getattr(target, "title", "") or "")
        return {
            "tab_id": tab_id,
            "index": index,
            "url": url,
            "title": title,
            "active": tab_id == active_id,
        }

    async def list_tabs(self) -> list[dict[str, Any]]:
        tabs = await self._page_tabs()
        if tabs and self.tab is None:
            self.tab = tabs[0]
        active_id = self._tab_id(self.tab) if self.tab is not None else None
        summaries = [
            self._tab_summary(tab, index=index, active_id=active_id)
            for index, tab in enumerate(tabs)
        ]
        if summaries and not any(row["active"] for row in summaries):
            self.tab = tabs[0]
            active_id = self._tab_id(self.tab)
            for row in summaries:
                row["active"] = row["tab_id"] == active_id
        return summaries

    async def new_tab(self, *, url: str = "about:blank", switch: bool = True) -> dict[str, Any]:
        if self.browser is None:
            raise RuntimeError("Browser not started")
        previous = self.tab
        created = await self.browser.get(url=url, new_tab=True)
        if switch:
            try:
                await created.activate()
            except Exception:
                pass
            self.tab = created
        elif previous is not None:
            try:
                await previous.activate()
            except Exception:
                pass
            self.tab = previous

        tabs = await self.list_tabs()
        created_id = self._tab_id(created)
        for row in tabs:
            if row["tab_id"] == created_id:
                return row
        return {
            "tab_id": created_id,
            "index": -1,
            "url": str(getattr(created, "url", "") or ""),
            "title": "",
            "active": bool(switch),
        }

    async def _resolve_tab(
        self,
        *,
        tab_id: str | None = None,
        index: int | None = None,
    ) -> tuple[Any, int]:
        if tab_id is not None and index is not None:
            raise ValueError("Provide either tab_id or index, not both.")
        if tab_id is None and index is None:
            raise ValueError("Provide tab_id or index.")

        tabs = await self._page_tabs()
        if tab_id is not None:
            for idx, tab in enumerate(tabs):
                if self._tab_id(tab) == tab_id:
                    return tab, idx
            raise ValueError(f"Tab not found: {tab_id}")

        resolved_index = int(index)  # type: ignore[arg-type]
        if resolved_index < 0 or resolved_index >= len(tabs):
            raise ValueError(f"Tab index out of range: {resolved_index}")
        return tabs[resolved_index], resolved_index

    async def switch_tab(
        self,
        *,
        tab_id: str | None = None,
        index: int | None = None,
    ) -> dict[str, Any]:
        target_tab, _ = await self._resolve_tab(tab_id=tab_id, index=index)
        try:
            await target_tab.activate()
        except Exception:
            pass
        self.tab = target_tab
        tabs = await self.list_tabs()
        active_id = self._tab_id(target_tab)
        for row in tabs:
            if row["tab_id"] == active_id:
                return row
        raise RuntimeError("Failed to activate requested tab.")

    async def close_tab(
        self,
        *,
        tab_id: str | None = None,
        index: int | None = None,
        switch_to: str = "last_active",
    ) -> dict[str, Any]:
        target_tab, _ = await self._resolve_tab(tab_id=tab_id, index=index)
        closing_id = self._tab_id(target_tab)
        current_id = self._tab_id(self.tab) if self.tab is not None else None
        await target_tab.close()
        await asyncio.sleep(0.1)

        remaining_tabs = await self._page_tabs()
        if not remaining_tabs:
            self.tab = None
            return {
                "closed_tab_id": closing_id,
                "new_active_tab_id": None,
            }

        if switch_to == "first":
            new_active = remaining_tabs[0]
        elif current_id and current_id != closing_id:
            existing = [tab for tab in remaining_tabs if self._tab_id(tab) == current_id]
            new_active = existing[0] if existing else remaining_tabs[-1]
        else:
            new_active = remaining_tabs[-1]

        try:
            await new_active.activate()
        except Exception:
            pass
        self.tab = new_active
        return {
            "closed_tab_id": closing_id,
            "new_active_tab_id": self._tab_id(new_active),
        }

    async def current_tab_summary(self) -> dict[str, Any]:
        tabs = await self.list_tabs()
        for row in tabs:
            if row["active"]:
                return row
        if tabs:
            return tabs[0]
        raise RuntimeError("No browser tab is currently available.")

    async def select_first(self, selectors: list[str]) -> Any | None:
        for selector in selectors:
            try:
                element = await self.tab.select(selector)
                if element:
                    return element
            except Exception:
                continue
        return None

    async def select_all(self, selector: str) -> list[Any]:
        elements = await self.tab.select_all(selector)
        return elements or []

    async def press_key(self, key: str, code: str, virtual_key_code: int) -> None:
        await self.tab.send(
            self._cdp_input.dispatch_key_event(
                type_="keyDown",
                key=key,
                code=code,
                windows_virtual_key_code=virtual_key_code,
                native_virtual_key_code=virtual_key_code,
            )
        )
        await asyncio.sleep(0.05)
        await self.tab.send(
            self._cdp_input.dispatch_key_event(
                type_="keyUp",
                key=key,
                code=code,
                windows_virtual_key_code=virtual_key_code,
                native_virtual_key_code=virtual_key_code,
            )
        )

    async def set_cookies(
        self,
        cookies: list[dict[str, Any]],
        *,
        fallback_domain: str | None = None,
    ) -> None:
        if not self.tab:
            raise RuntimeError("Browser not started")

        await self.goto("about:blank", wait_seconds=0.5)
        for cookie in cookies:
            name = cookie.get("name")
            value = cookie.get("value", "")
            if not name:
                continue
            domain = cookie.get("domain") or fallback_domain
            if not domain:
                logger.debug("Skipping cookie '%s': missing domain", name)
                continue
            try:
                await self.tab.send(
                    self._cdp_network.set_cookie(
                        name=name,
                        value=value,
                        domain=domain,
                        path=cookie.get("path", "/"),
                        secure=bool(cookie.get("secure", False)),
                        http_only=bool(cookie.get("httpOnly", False)),
                    )
                )
            except Exception as exc:
                logger.debug("Skipping cookie '%s': %s", name, exc)

    async def get_cookies(self) -> list[dict[str, Any]]:
        response = await self.tab.send(self._cdp_storage.get_cookies())
        raw_cookies = response if isinstance(response, list) else getattr(response, "cookies", [])
        return [self._cookie_to_dict(cookie) for cookie in raw_cookies or []]

    @staticmethod
    def _cookie_to_dict(cookie: Any) -> dict[str, Any]:
        if isinstance(cookie, dict):
            return cookie
        result: dict[str, Any] = {}
        fields = [
            "name",
            "value",
            "domain",
            "path",
            "secure",
            "httpOnly",
            "expires",
            "sameSite",
        ]
        for field in fields:
            if hasattr(cookie, field):
                result[field] = getattr(cookie, field)
        return result

    @property
    def connection_host(self) -> str | None:
        config = getattr(self.browser, "config", None)
        host = getattr(config, "host", None)
        return str(host) if host is not None else None

    @property
    def connection_port(self) -> int | None:
        config = getattr(self.browser, "config", None)
        port = getattr(config, "port", None)
        return int(port) if port is not None else None

    @property
    def websocket_url(self) -> str | None:
        if self.browser is None:
            return None
        raw = getattr(self.browser, "websocket_url", None)
        if raw is None:
            return None
        return str(raw)
