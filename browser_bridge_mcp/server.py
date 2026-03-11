"""MCP server exposing nodriver-based browser bridge tools."""

from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from .actions import (
    DEFAULT_ACTION_LIMIT,
    DEFAULT_ACTION_WAIT_SECONDS,
    DEFAULT_EVENT_LIMIT,
    DEFAULT_HTML_LIMIT,
    click_selector,
    get_console_messages,
    get_network_requests,
    get_page_html,
    get_url_and_title,
    navigate_back,
    navigate_forward,
    navigate_to,
    normalize_evaluate_payload,
    query_selector,
    reload_page,
    scroll_page,
    snapshot_interactive,
    take_screenshot,
    type_into_selector,
    wait_for_selector,
    wait_seconds as wait_for_seconds,
)
from .runtime import BrowserSessionManager


SERVER_NAME = "browser-bridge-mcp"


def create_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    log_level: str = "INFO",
) -> FastMCP:
    manager = BrowserSessionManager()

    @asynccontextmanager
    async def lifespan(_: FastMCP):
        try:
            yield
        finally:
            await manager.stop_all_sessions()

    mcp = FastMCP(
        name=SERVER_NAME,
        instructions=(
            "Bridge MCP server for stealthed nodriver browser automation. "
            "Launch or attach browser sessions and use browser_* tools to inspect DOM state, "
            "navigate, click, type, scroll, capture console/network metadata, and take screenshots."
        ),
        host=host,
        port=port,
        log_level=log_level,  # type: ignore[arg-type]
        lifespan=lifespan,
    )

    @mcp.tool(name="session_start", description="Launch a new browser session.")
    async def session_start(
        session_id: str | None = None,
        headless: bool = False,
        start_url: str | None = "about:blank",
        user_data_dir: str | None = None,
        browser_args: list[str] | None = None,
        browser_executable_path: str | None = None,
        sandbox: bool = True,
        cookie_file: str | None = None,
        cookie_fallback_domain: str | None = None,
    ) -> dict[str, Any]:
        return await manager.start_session(
            session_id=session_id,
            headless=headless,
            start_url=start_url,
            user_data_dir=user_data_dir,
            browser_args=browser_args,
            browser_executable_path=browser_executable_path,
            sandbox=sandbox,
            cookie_file=cookie_file,
            cookie_fallback_domain=cookie_fallback_domain,
        )

    @mcp.tool(
        name="session_attach",
        description="Attach to existing browser via host/port, ws_url, or state_file.",
    )
    async def session_attach(
        session_id: str | None = None,
        host: str | None = None,
        port: int | None = None,
        ws_url: str | None = None,
        state_file: str | None = None,
        start_url: str | None = None,
    ) -> dict[str, Any]:
        return await manager.attach_session(
            session_id=session_id,
            host=host,
            port=port,
            ws_url=ws_url,
            state_file=state_file,
            start_url=start_url,
        )

    @mcp.tool(name="session_list", description="List active browser sessions.")
    async def session_list() -> dict[str, Any]:
        sessions = await manager.list_sessions()
        return {"count": len(sessions), "sessions": sessions}

    @mcp.tool(name="session_get", description="Get one session summary.")
    async def session_get(session_id: str) -> dict[str, Any]:
        session = await manager.get_session(session_id)
        return session.summary()

    @mcp.tool(name="session_stop", description="Stop one session by id.")
    async def session_stop(session_id: str) -> dict[str, Any]:
        return await manager.stop_session(session_id=session_id)

    @mcp.tool(name="session_stop_all", description="Stop all active sessions.")
    async def session_stop_all() -> dict[str, Any]:
        return await manager.stop_all_sessions()

    @mcp.tool(name="browser_url", description="Get current URL and page title.")
    async def browser_url(session_id: str) -> dict[str, Any]:
        return await manager.run_action(
            session_id=session_id,
            action_name="browser_url",
            operation=get_url_and_title,
        )

    @mcp.tool(name="browser_navigate", description="Navigate to a URL.")
    async def browser_navigate(
        session_id: str,
        url: str,
        wait_seconds: float = DEFAULT_ACTION_WAIT_SECONDS,
    ) -> dict[str, Any]:
        return await manager.run_action(
            session_id=session_id,
            action_name="browser_navigate",
            operation=lambda browser: navigate_to(
                browser,
                url=url,
                wait_seconds=wait_seconds,
            ),
        )

    @mcp.tool(name="browser_back", description="Navigate one step back in browser history.")
    async def browser_back(
        session_id: str,
        wait_seconds: float = DEFAULT_ACTION_WAIT_SECONDS,
    ) -> dict[str, Any]:
        return await manager.run_action(
            session_id=session_id,
            action_name="browser_back",
            operation=lambda browser: navigate_back(
                browser,
                wait_seconds=wait_seconds,
            ),
        )

    @mcp.tool(name="browser_forward", description="Navigate one step forward in browser history.")
    async def browser_forward(
        session_id: str,
        wait_seconds: float = DEFAULT_ACTION_WAIT_SECONDS,
    ) -> dict[str, Any]:
        return await manager.run_action(
            session_id=session_id,
            action_name="browser_forward",
            operation=lambda browser: navigate_forward(
                browser,
                wait_seconds=wait_seconds,
            ),
        )

    @mcp.tool(name="browser_reload", description="Reload the current page.")
    async def browser_reload(
        session_id: str,
        wait_seconds: float = DEFAULT_ACTION_WAIT_SECONDS,
        ignore_cache: bool = False,
    ) -> dict[str, Any]:
        return await manager.run_action(
            session_id=session_id,
            action_name="browser_reload",
            operation=lambda browser: reload_page(
                browser,
                wait_seconds=wait_seconds,
                ignore_cache=ignore_cache,
            ),
        )

    @mcp.tool(
        name="browser_snapshot",
        description="Return a compact snapshot of interactive elements on the page.",
    )
    async def browser_snapshot(
        session_id: str,
        limit: int = DEFAULT_ACTION_LIMIT,
    ) -> dict[str, Any]:
        return await manager.run_action(
            session_id=session_id,
            action_name="browser_snapshot",
            operation=lambda browser: snapshot_interactive(browser, limit=limit),
        )

    @mcp.tool(name="browser_query", description="Query DOM elements by CSS selector.")
    async def browser_query(
        session_id: str,
        selector: str,
        limit: int = DEFAULT_ACTION_LIMIT,
    ) -> dict[str, Any]:
        return await manager.run_action(
            session_id=session_id,
            action_name="browser_query",
            operation=lambda browser: query_selector(
                browser,
                selector=selector,
                limit=limit,
            ),
        )

    @mcp.tool(name="browser_click", description="Click the first matching selector.")
    async def browser_click(
        session_id: str,
        selector: str,
        wait_seconds: float = DEFAULT_ACTION_WAIT_SECONDS,
    ) -> dict[str, Any]:
        return await manager.run_action(
            session_id=session_id,
            action_name="browser_click",
            operation=lambda browser: click_selector(
                browser,
                selector=selector,
                wait_seconds=wait_seconds,
            ),
        )

    @mcp.tool(name="browser_type", description="Type text into an input selector.")
    async def browser_type(
        session_id: str,
        selector: str,
        text: str,
        clear: bool = False,
        submit: bool = False,
        wait_seconds: float = DEFAULT_ACTION_WAIT_SECONDS,
    ) -> dict[str, Any]:
        return await manager.run_action(
            session_id=session_id,
            action_name="browser_type",
            operation=lambda browser: type_into_selector(
                browser,
                selector=selector,
                text=text,
                clear=clear,
                submit=submit,
                wait_seconds=wait_seconds,
            ),
        )

    @mcp.tool(name="browser_scroll", description="Scroll page, to top, to bottom, or to selector.")
    async def browser_scroll(
        session_id: str,
        selector: str | None = None,
        delta_y: int = 1200,
        to_top: bool = False,
        to_bottom: bool = False,
        wait_seconds: float = DEFAULT_ACTION_WAIT_SECONDS,
    ) -> dict[str, Any]:
        return await manager.run_action(
            session_id=session_id,
            action_name="browser_scroll",
            operation=lambda browser: scroll_page(
                browser,
                selector=selector,
                delta_y=delta_y,
                to_top=to_top,
                to_bottom=to_bottom,
                wait_seconds=wait_seconds,
            ),
        )

    @mcp.tool(name="browser_wait_for_selector", description="Wait until selector appears or timeout.")
    async def browser_wait_for_selector_tool(
        session_id: str,
        selector: str,
        timeout_seconds: float = 10.0,
    ) -> dict[str, Any]:
        return await manager.run_action(
            session_id=session_id,
            action_name="browser_wait_for_selector",
            operation=lambda browser: wait_for_selector(
                browser,
                selector=selector,
                timeout_seconds=timeout_seconds,
            ),
        )

    @mcp.tool(name="browser_wait", description="Wait for a number of seconds.")
    async def browser_wait(
        session_id: str,
        seconds: float = DEFAULT_ACTION_WAIT_SECONDS,
    ) -> dict[str, Any]:
        return await manager.run_action(
            session_id=session_id,
            action_name="browser_wait",
            operation=lambda _: wait_for_seconds(seconds),
        )

    @mcp.tool(name="browser_html", description="Return current page HTML (optionally truncated).")
    async def browser_html(
        session_id: str,
        max_chars: int = DEFAULT_HTML_LIMIT,
    ) -> dict[str, Any]:
        return await manager.run_action(
            session_id=session_id,
            action_name="browser_html",
            operation=lambda browser: get_page_html(browser, max_chars=max_chars),
        )

    @mcp.tool(name="browser_console_messages", description="Read captured in-page console messages.")
    async def browser_console_messages(
        session_id: str,
        limit: int = DEFAULT_EVENT_LIMIT,
        clear: bool = False,
    ) -> dict[str, Any]:
        return await manager.run_action(
            session_id=session_id,
            action_name="browser_console_messages",
            operation=lambda browser: get_console_messages(
                browser,
                limit=limit,
                clear=clear,
            ),
        )

    @mcp.tool(name="browser_network_requests", description="Read captured fetch/xhr request metadata.")
    async def browser_network_requests(
        session_id: str,
        limit: int = DEFAULT_EVENT_LIMIT,
        clear: bool = False,
    ) -> dict[str, Any]:
        return await manager.run_action(
            session_id=session_id,
            action_name="browser_network_requests",
            operation=lambda browser: get_network_requests(
                browser,
                limit=limit,
                clear=clear,
            ),
        )

    @mcp.tool(name="browser_take_screenshot", description="Capture a screenshot to disk.")
    async def browser_take_screenshot(
        session_id: str,
        output_path: str,
        full_page: bool = False,
        image_format: str = "png",
    ) -> dict[str, Any]:
        return await manager.run_action(
            session_id=session_id,
            action_name="browser_take_screenshot",
            operation=lambda browser: take_screenshot(
                browser,
                output_path=output_path,
                full_page=full_page,
                image_format=image_format,
            ),
        )

    @mcp.tool(name="browser_evaluate", description="Evaluate JavaScript in current page.")
    async def browser_evaluate(
        session_id: str,
        script: str,
    ) -> dict[str, Any]:
        async def _operation(browser) -> dict[str, Any]:
            result = await browser.evaluate(script)
            return {"result": normalize_evaluate_payload(result)}

        return await manager.run_action(
            session_id=session_id,
            action_name="browser_evaluate",
            operation=_operation,
        )

    return mcp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="browser-bridge-mcp",
        description="Stealth browser bridge MCP server for nodriver sessions.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport type",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for HTTP transports")
    parser.add_argument("--port", type=int, default=8000, help="Port for HTTP transports")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Server log level",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    server = create_server(host=args.host, port=args.port, log_level=args.log_level)
    try:
        server.run(transport=args.transport)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
