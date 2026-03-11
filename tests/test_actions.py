import unittest

from browser_bridge_mcp.actions import (
    navigate_back,
    navigate_forward,
    normalize_evaluate_payload,
    reload_page,
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


if __name__ == "__main__":
    unittest.main()
