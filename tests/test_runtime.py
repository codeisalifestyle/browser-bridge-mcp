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


if __name__ == "__main__":
    unittest.main()
