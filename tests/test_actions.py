import unittest
from unittest.mock import AsyncMock, patch

from browser_bridge_mcp.actions import (
    close_tab,
    current_tab,
    get_downloads,
    handle_dialog,
    list_tabs,
    navigate_back,
    navigate_forward,
    new_tab,
    normalize_evaluate_payload,
    reload_page,
    set_download_dir,
    set_file_input,
    switch_tab,
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


class _FakeTabActionBrowser:
    def __init__(self) -> None:
        self.tab = _FakeTab("https://example.com/a")
        self._title = "A"
        self.new_args: tuple[str, bool] | None = None
        self.switch_args: tuple[str | None, int | None] | None = None
        self.close_args: tuple[str | None, int | None, str] | None = None

    async def evaluate(self, script: str):
        if script == "document.title":
            return self._title
        raise AssertionError(f"Unexpected script: {script}")

    async def list_tabs(self) -> list[dict[str, object]]:
        return [
            {
                "tab_id": "tab-a",
                "index": 0,
                "url": "https://example.com/a",
                "title": "A",
                "active": True,
            },
            {
                "tab_id": "tab-b",
                "index": 1,
                "url": "https://example.com/b",
                "title": "B",
                "active": False,
            },
        ]

    async def new_tab(self, *, url: str = "about:blank", switch: bool = True) -> dict[str, object]:
        self.new_args = (url, switch)
        return {
            "tab_id": "tab-b",
            "index": 1,
            "url": "https://example.com/b",
            "title": "B",
            "active": bool(switch),
        }

    async def switch_tab(
        self,
        *,
        tab_id: str | None = None,
        index: int | None = None,
    ) -> dict[str, object]:
        self.switch_args = (tab_id, index)
        self.tab.url = "https://example.com/b"
        self._title = "B"
        return {
            "tab_id": "tab-b",
            "index": 1,
            "url": "https://example.com/b",
            "title": "B",
            "active": True,
        }

    async def close_tab(
        self,
        *,
        tab_id: str | None = None,
        index: int | None = None,
        switch_to: str = "last_active",
    ) -> dict[str, object]:
        self.close_args = (tab_id, index, switch_to)
        self.tab.url = "https://example.com/a"
        self._title = "A"
        return {
            "closed_tab_id": "tab-b",
            "new_active_tab_id": "tab-a",
        }

    async def current_tab_summary(self) -> dict[str, object]:
        return {
            "tab_id": "tab-a",
            "index": 0,
            "url": "https://example.com/a",
            "title": "A",
            "active": True,
        }


class _FakeDialogUploadBrowser:
    def __init__(self) -> None:
        self.tab = _FakeTab("https://example.com/form")
        self._title = "Form"
        self.dialog_args: tuple[bool, str | None, bool] | None = None
        self.file_input_args: tuple[str, list[str]] | None = None
        self.download_dir_arg: str | None = None
        self.download_query_args: tuple[int, bool] | None = None

    async def evaluate(self, script: str):
        if script == "document.title":
            return self._title
        raise AssertionError(f"Unexpected script: {script}")

    async def set_dialog_handler(
        self,
        *,
        accept: bool = True,
        prompt_text: str | None = None,
        once: bool = True,
    ) -> dict[str, object]:
        self.dialog_args = (accept, prompt_text, once)
        return {
            "accept": accept,
            "prompt_text": prompt_text,
            "once": once,
        }

    async def set_file_input(self, *, selector: str, file_paths: list[str]) -> list[str]:
        self.file_input_args = (selector, file_paths)
        return list(file_paths)

    async def set_download_dir(self, *, download_dir: str) -> str:
        self.download_dir_arg = download_dir
        return download_dir

    async def get_downloads(self, *, limit: int = 100, clear: bool = False) -> dict[str, object]:
        self.download_query_args = (limit, clear)
        return {
            "returned": 1,
            "total_available": 1,
            "rows": [{"guid": "dl-1", "state": "completed"}],
        }


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


class TabActionsTest(unittest.IsolatedAsyncioTestCase):
    async def test_list_tabs_returns_count(self) -> None:
        browser = _FakeTabActionBrowser()
        payload = await list_tabs(browser)
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["tabs"][0]["tab_id"], "tab-a")

    async def test_new_tab_returns_created_tab_id(self) -> None:
        browser = _FakeTabActionBrowser()
        payload = await new_tab(
            browser,
            url="https://example.com/b",
            switch=True,
            wait_seconds=0,
        )
        self.assertEqual(payload["created_tab_id"], "tab-b")
        self.assertEqual(browser.new_args, ("https://example.com/b", True))

    async def test_switch_tab_returns_active_tab(self) -> None:
        browser = _FakeTabActionBrowser()
        payload = await switch_tab(browser, index=1, wait_seconds=0)
        self.assertEqual(payload["tab"]["tab_id"], "tab-b")
        self.assertEqual(browser.switch_args, (None, 1))
        self.assertEqual(payload["url"], "https://example.com/b")

    async def test_close_tab_returns_close_metadata(self) -> None:
        browser = _FakeTabActionBrowser()
        payload = await close_tab(browser, tab_id="tab-b", switch_to="last_active")
        self.assertEqual(payload["closed_tab_id"], "tab-b")
        self.assertEqual(payload["new_active_tab_id"], "tab-a")
        self.assertEqual(browser.close_args, ("tab-b", None, "last_active"))

    async def test_current_tab_returns_active_summary(self) -> None:
        browser = _FakeTabActionBrowser()
        payload = await current_tab(browser)
        self.assertEqual(payload["tab"]["tab_id"], "tab-a")
        self.assertEqual(payload["url"], "https://example.com/a")


class DialogUploadDownloadActionsTest(unittest.IsolatedAsyncioTestCase):
    async def test_handle_dialog_configures_dialog_behavior(self) -> None:
        browser = _FakeDialogUploadBrowser()
        payload = await handle_dialog(browser, accept=False, prompt_text="hello", once=True)
        self.assertTrue(payload["configured"])
        self.assertFalse(payload["accept"])
        self.assertEqual(payload["prompt_text"], "hello")
        self.assertEqual(browser.dialog_args, (False, "hello", True))

    async def test_set_file_input_reports_uploaded_files(self) -> None:
        browser = _FakeDialogUploadBrowser()
        payload = await set_file_input(
            browser,
            selector='input[type="file"]',
            file_paths=["/tmp/a.txt", "/tmp/b.txt"],
            wait_seconds=0,
        )
        self.assertEqual(payload["files_set_count"], 2)
        self.assertEqual(payload["selector"], 'input[type="file"]')
        self.assertEqual(
            browser.file_input_args,
            ('input[type="file"]', ["/tmp/a.txt", "/tmp/b.txt"]),
        )

    async def test_set_download_dir_returns_path(self) -> None:
        browser = _FakeDialogUploadBrowser()
        payload = await set_download_dir(browser, download_dir="/tmp/downloads")
        self.assertEqual(payload["download_dir"], "/tmp/downloads")
        self.assertEqual(browser.download_dir_arg, "/tmp/downloads")

    async def test_get_downloads_returns_rows(self) -> None:
        browser = _FakeDialogUploadBrowser()
        payload = await get_downloads(browser, limit=10, clear=True)
        self.assertEqual(payload["returned"], 1)
        self.assertEqual(payload["rows"][0]["guid"], "dl-1")
        self.assertEqual(browser.download_query_args, (10, True))


if __name__ == "__main__":
    unittest.main()
