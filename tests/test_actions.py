import unittest
from unittest.mock import AsyncMock, patch

from browser_bridge_mcp.actions import (
    navigate_back,
    navigate_forward,
    normalize_evaluate_payload,
    reload_page,
    wait_for_function,
    wait_for_network_idle,
    wait_for_text,
    wait_for_url,
)


class _FakeTab:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakeBrowser:
    def __init__(self) -> None:
        self.tab = _FakeTab("https://example.com/two")
        self._title = "Two"
        self.back_changes = True
        self.forward_changes = True
        self.reload_ignore_cache = False

    async def evaluate(self, script: str):
        if script == "document.title":
            return self._title
        raise AssertionError(f"Unexpected script: {script}")

    async def go_back(self) -> None:
        if self.back_changes:
            self.tab.url = "https://example.com/one"
            self._title = "One"

    async def go_forward(self) -> None:
        if self.forward_changes:
            self.tab.url = "https://example.com/two"
            self._title = "Two"

    async def reload(self, *, ignore_cache: bool = False) -> None:
        self.reload_ignore_cache = ignore_cache


class _FakeEvaluateBrowser:
    def __init__(self, results: list[object]) -> None:
        self._results = list(results)

    async def evaluate(self, _script: str):
        if not self._results:
            raise AssertionError("No scripted evaluate result available.")
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class NormalizeEvaluatePayloadTest(unittest.TestCase):
    def test_normalizes_object_pairs(self) -> None:
        payload = [
            ["name", {"type": "string", "value": "Alice"}],
            [
                "items",
                {
                    "type": "array",
                    "value": [
                        {"type": "number", "value": 1},
                        {"type": "number", "value": 2},
                    ],
                },
            ],
        ]
        value = normalize_evaluate_payload(payload)
        self.assertEqual(value["name"], "Alice")
        self.assertEqual(value["items"], [1, 2])

    def test_normalizes_nested_object_wrapper(self) -> None:
        payload = {
            "type": "object",
            "value": [
                ["ok", {"type": "boolean", "value": True}],
                ["count", {"type": "number", "value": 3}],
            ],
        }
        value = normalize_evaluate_payload(payload)
        self.assertEqual(value, {"ok": True, "count": 3})


class NavigationActionsTest(unittest.IsolatedAsyncioTestCase):
    async def test_navigate_back_marks_navigated_on_change(self) -> None:
        browser = _FakeBrowser()
        payload = await navigate_back(browser, wait_seconds=0)
        self.assertTrue(payload["navigated"])
        self.assertEqual(payload["url"], "https://example.com/one")
        self.assertEqual(payload["title"], "One")

    async def test_navigate_back_marks_not_navigated_without_change(self) -> None:
        browser = _FakeBrowser()
        browser.back_changes = False
        payload = await navigate_back(browser, wait_seconds=0)
        self.assertFalse(payload["navigated"])
        self.assertEqual(payload["url"], "https://example.com/two")
        self.assertEqual(payload["title"], "Two")

    async def test_navigate_forward_marks_navigated_on_change(self) -> None:
        browser = _FakeBrowser()
        await browser.go_back()
        payload = await navigate_forward(browser, wait_seconds=0)
        self.assertTrue(payload["navigated"])
        self.assertEqual(payload["url"], "https://example.com/two")
        self.assertEqual(payload["title"], "Two")

    async def test_reload_page_returns_reload_metadata(self) -> None:
        browser = _FakeBrowser()
        payload = await reload_page(browser, wait_seconds=0, ignore_cache=True)
        self.assertTrue(payload["reloaded"])
        self.assertTrue(payload["ignore_cache"])
        self.assertTrue(browser.reload_ignore_cache)


class WaitActionsTest(unittest.IsolatedAsyncioTestCase):
    async def test_wait_for_url_matches_substring(self) -> None:
        with patch(
            "browser_bridge_mcp.actions.get_url_and_title",
            new=AsyncMock(
                side_effect=[
                    {"url": "https://example.com/login", "title": "Login"},
                    {"url": "https://example.com/dashboard", "title": "Dashboard"},
                ]
            ),
        ):
            payload = await wait_for_url(
                object(),
                url_contains="dashboard",
                timeout_seconds=0.3,
                poll_interval_seconds=0.01,
            )
        self.assertTrue(payload["matched"])
        self.assertEqual(payload["url"], "https://example.com/dashboard")

    async def test_wait_for_url_timeout_returns_error(self) -> None:
        with patch(
            "browser_bridge_mcp.actions.get_url_and_title",
            new=AsyncMock(return_value={"url": "https://example.com/login", "title": "Login"}),
        ):
            payload = await wait_for_url(
                object(),
                url_contains="dashboard",
                timeout_seconds=0.12,
                poll_interval_seconds=0.01,
            )
        self.assertFalse(payload["matched"])
        self.assertIn("error", payload)

    async def test_wait_for_text_eventually_finds_text(self) -> None:
        browser = _FakeEvaluateBrowser(
            [
                {"found": False},
                {"found": True},
            ]
        )
        with patch(
            "browser_bridge_mcp.actions.get_url_and_title",
            new=AsyncMock(return_value={"url": "https://example.com", "title": "Home"}),
        ):
            payload = await wait_for_text(
                browser,
                text="Ready",
                selector="#status",
                timeout_seconds=0.3,
                poll_interval_seconds=0.01,
            )
        self.assertTrue(payload["found"])
        self.assertEqual(payload["selector"], "#status")

    async def test_wait_for_function_eventually_truthy(self) -> None:
        browser = _FakeEvaluateBrowser([0, "", {"ok": True}])
        with patch(
            "browser_bridge_mcp.actions.get_url_and_title",
            new=AsyncMock(return_value={"url": "https://example.com", "title": "Home"}),
        ):
            payload = await wait_for_function(
                browser,
                script="window.__ready",
                timeout_seconds=0.3,
                poll_interval_seconds=0.01,
            )
        self.assertTrue(payload["truthy"])
        self.assertEqual(payload["result"], {"ok": True})

    async def test_wait_for_network_idle_returns_idle_state(self) -> None:
        browser = _FakeEvaluateBrowser(
            [
                {"in_flight": 2, "idle_for_ms": 120},
                {"in_flight": 0, "idle_for_ms": 650},
            ]
        )
        with (
            patch("browser_bridge_mcp.actions.ensure_observers", new=AsyncMock()),
            patch(
                "browser_bridge_mcp.actions.get_url_and_title",
                new=AsyncMock(return_value={"url": "https://example.com", "title": "Home"}),
            ),
        ):
            payload = await wait_for_network_idle(
                browser,
                idle_ms=500,
                timeout_seconds=0.3,
                max_inflight=0,
                poll_interval_seconds=0.01,
            )
        self.assertTrue(payload["idle"])
        self.assertEqual(payload["inflight_peak"], 2)


if __name__ == "__main__":
    unittest.main()
