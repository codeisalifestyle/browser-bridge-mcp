import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from browser_bridge_mcp.runtime import BrowserSession, BrowserSessionManager, resolve_connection


class ResolveConnectionTest(unittest.TestCase):
    def test_host_port_mode(self) -> None:
        host, port = resolve_connection(
            host="127.0.0.1",
            port=9222,
            ws_url=None,
            state_file=None,
        )
        self.assertEqual(host, "127.0.0.1")
        self.assertEqual(port, 9222)

    def test_ws_url_mode(self) -> None:
        host, port = resolve_connection(
            host=None,
            port=None,
            ws_url="ws://127.0.0.1:65427/devtools/browser/abc",
            state_file=None,
        )
        self.assertEqual(host, "127.0.0.1")
        self.assertEqual(port, 65427)

    def test_state_file_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(
                json.dumps({"host": "127.0.0.1", "port": 9444}),
                encoding="utf-8",
            )
            host, port = resolve_connection(
                host=None,
                port=None,
                ws_url=None,
                state_file=str(state_path),
            )
            self.assertEqual(host, "127.0.0.1")
            self.assertEqual(port, 9444)

    def test_requires_single_connection_mode(self) -> None:
        with self.assertRaises(ValueError):
            resolve_connection(
                host="127.0.0.1",
                port=9222,
                ws_url="ws://127.0.0.1:9222/devtools/browser/abc",
                state_file=None,
            )


class SessionPolicyRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def _build_manager_with_session(
        self,
        *,
        policy: dict | None = None,
        last_known_url: str | None = "https://example.com/home",
    ) -> BrowserSessionManager:
        manager = BrowserSessionManager()
        session = BrowserSession(
            session_id="sess_123",
            browser=object(),  # type: ignore[arg-type]
            mode="launch",
            created_at="2026-01-01T00:00:00+00:00",
            headless=False,
            connection_host=None,
            connection_port=None,
            websocket_url=None,
            metadata={},
            last_known_url=last_known_url,
            last_known_title="Home",
            policy=policy or {},
        )
        await manager._insert_session(session)
        return manager

    async def test_set_and_get_policy(self) -> None:
        manager = await self._build_manager_with_session()
        updated = await manager.set_policy(
            session_id="sess_123",
            allowed_domains=["example.com", "https://api.example.com/path"],
            blocked_domains=["bad.com"],
            read_only=True,
            allow_evaluate=False,
        )
        self.assertEqual(updated["policy"]["allowed_domains"], ["api.example.com", "example.com"])
        self.assertEqual(updated["policy"]["blocked_domains"], ["bad.com"])
        self.assertTrue(updated["policy"]["read_only"])
        self.assertFalse(updated["policy"]["allow_evaluate"])

        current = await manager.get_policy(session_id="sess_123")
        self.assertEqual(current["policy"], updated["policy"])

    async def test_read_only_policy_blocks_mutating_actions(self) -> None:
        manager = await self._build_manager_with_session(policy={"read_only": True})
        operation = AsyncMock(return_value={"ok": True})
        response = await manager.run_action(
            session_id="sess_123",
            action_name="browser_click",
            operation=operation,
        )
        self.assertFalse(response["allowed"])
        self.assertEqual(response["reason_code"], "read_only_block")
        operation.assert_not_awaited()

    async def test_allow_evaluate_false_blocks_browser_evaluate(self) -> None:
        manager = await self._build_manager_with_session(policy={"allow_evaluate": False})
        operation = AsyncMock(return_value={"ok": True})
        response = await manager.run_action(
            session_id="sess_123",
            action_name="browser_evaluate",
            operation=operation,
        )
        self.assertFalse(response["allowed"])
        self.assertEqual(response["reason_code"], "evaluate_blocked")
        operation.assert_not_awaited()

    async def test_allowed_domains_blocks_external_navigation(self) -> None:
        manager = await self._build_manager_with_session(
            policy={"allowed_domains": ["example.com"], "blocked_domains": []}
        )
        operation = AsyncMock(return_value={"ok": True})
        response = await manager.run_action(
            session_id="sess_123",
            action_name="browser_navigate",
            action_args={"url": "https://forbidden.dev/path"},
            operation=operation,
        )
        self.assertFalse(response["allowed"])
        self.assertEqual(response["reason_code"], "domain_not_allowed")
        operation.assert_not_awaited()

    async def test_blocked_domains_block_actions_on_current_page(self) -> None:
        manager = await self._build_manager_with_session(
            policy={"blocked_domains": ["evil.com"], "allowed_domains": None},
            last_known_url="https://evil.com/dashboard",
        )
        operation = AsyncMock(return_value={"ok": True})
        response = await manager.run_action(
            session_id="sess_123",
            action_name="browser_click",
            operation=operation,
        )
        self.assertFalse(response["allowed"])
        self.assertEqual(response["reason_code"], "domain_blocked")
        operation.assert_not_awaited()

    async def test_policy_allows_action_when_domain_matches_allowlist(self) -> None:
        manager = await self._build_manager_with_session(
            policy={"allowed_domains": ["example.com"], "blocked_domains": []}
        )
        operation = AsyncMock(return_value={"url": "https://example.com/next", "title": "Next"})
        response = await manager.run_action(
            session_id="sess_123",
            action_name="browser_click",
            operation=operation,
        )
        self.assertEqual(response["url"], "https://example.com/next")
        self.assertEqual(response["title"], "Next")
        operation.assert_awaited_once()


class SessionTraceRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def _build_manager_with_session(self) -> BrowserSessionManager:
        manager = BrowserSessionManager()
        session = BrowserSession(
            session_id="sess_trace",
            browser=object(),  # type: ignore[arg-type]
            mode="launch",
            created_at="2026-01-01T00:00:00+00:00",
            headless=False,
            connection_host=None,
            connection_port=None,
            websocket_url=None,
            metadata={},
            last_known_url="https://example.com/home",
            last_known_title="Home",
            policy={},
        )
        await manager._insert_session(session)
        return manager

    async def test_trace_records_successful_action(self) -> None:
        manager = await self._build_manager_with_session()
        await manager.start_trace(
            session_id="sess_trace",
            trace_id="trace_test",
            capture_screenshot_on_error=False,
            capture_html_on_error=False,
        )
        operation = AsyncMock(return_value={"url": "https://example.com/next", "title": "Next"})
        await manager.run_action(
            session_id="sess_trace",
            action_name="browser_click",
            action_args={"selector": "#submit"},
            operation=operation,
        )
        trace = await manager.get_trace_events(session_id="sess_trace")
        self.assertEqual(trace["total_available"], 1)
        self.assertEqual(trace["events"][0]["action"], "browser_click")
        self.assertEqual(trace["events"][0]["inputs"]["selector"], "#submit")

    async def test_trace_records_errors(self) -> None:
        manager = await self._build_manager_with_session()
        await manager.start_trace(
            session_id="sess_trace",
            capture_screenshot_on_error=False,
            capture_html_on_error=False,
        )

        async def failing_operation(_browser):
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            await manager.run_action(
                session_id="sess_trace",
                action_name="browser_click",
                operation=failing_operation,
            )
        trace = await manager.get_trace_events(session_id="sess_trace")
        self.assertEqual(trace["total_available"], 1)
        self.assertIn("boom", trace["events"][0]["error"])

    async def test_trace_export_writes_file(self) -> None:
        manager = await self._build_manager_with_session()
        await manager.start_trace(session_id="sess_trace")
        operation = AsyncMock(return_value={"url": "https://example.com/next", "title": "Next"})
        await manager.run_action(
            session_id="sess_trace",
            action_name="browser_click",
            operation=operation,
        )
        await manager.stop_trace(session_id="sess_trace")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = str(Path(tmpdir) / "trace.json")
            exported = await manager.export_trace(
                session_id="sess_trace",
                output_path=output_path,
            )
            self.assertEqual(exported["event_count"], 1)
            self.assertTrue(Path(output_path).exists())
            self.assertEqual(len(exported["checksum"]), 64)

    async def test_trace_replay_dry_run_reports_supported_and_skipped(self) -> None:
        manager = await self._build_manager_with_session()
        trace_payload = {
            "trace_version": "1.0",
            "session_id": "sess_trace",
            "events": [
                {"action": "browser_navigate", "inputs": {"url": "https://example.com"}},
                {"action": "unsupported_action", "inputs": {}},
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "trace.json"
            trace_path.write_text(json.dumps(trace_payload), encoding="utf-8")
            replay = await manager.replay_trace(
                trace_path=str(trace_path),
                session_id="sess_trace",
                dry_run=True,
            )
            self.assertEqual(replay["passed"], 1)
            self.assertEqual(replay["skipped"], 1)

    async def test_trace_replay_executes_supported_wait_action(self) -> None:
        manager = await self._build_manager_with_session()
        trace_payload = {
            "trace_version": "1.0",
            "session_id": "sess_trace",
            "events": [
                {"action": "browser_wait", "inputs": {"seconds": 0}},
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "trace.json"
            trace_path.write_text(json.dumps(trace_payload), encoding="utf-8")
            replay = await manager.replay_trace(
                trace_path=str(trace_path),
                session_id="sess_trace",
                stop_on_error=True,
                dry_run=False,
            )
            self.assertEqual(replay["passed"], 1)
            self.assertEqual(replay["failed"], 0)


if __name__ == "__main__":
    unittest.main()
