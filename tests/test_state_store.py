import tempfile
import unittest

from browser_bridge_mcp.runtime import BrowserSessionManager
from browser_bridge_mcp.state_store import BrowserStateStore


class StateStoreTest(unittest.TestCase):
    def test_launch_config_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = BrowserStateStore(state_root=tmpdir)
            saved = store.set_launch_config(
                config_name="default",
                values={
                    "headless": True,
                    "start_url": "https://example.com",
                    "browser_args": ["--lang=en-US"],
                },
            )
            self.assertTrue(saved["exists"])
            self.assertTrue(saved["values"]["headless"])
            self.assertEqual(saved["values"]["start_url"], "https://example.com")
            self.assertEqual(saved["values"]["browser_args"], ["--lang=en-US"])

            fetched = store.get_launch_config("default")
            self.assertEqual(fetched["values"], saved["values"])
            self.assertEqual(fetched["effective_values"]["start_url"], "https://example.com")

    def test_profile_alias_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = BrowserStateStore(state_root=tmpdir)
            store.set_profile(
                profile_name="twitter_main",
                account_aliases=["twitter", "@acme_social"],
                cookie_name="twitter_cookies",
            )
            by_alias = store.resolve_profile_reference("@acme_social")
            self.assertEqual(by_alias["name"], "twitter_main")
            self.assertEqual(by_alias["cookie_name"], "twitter_cookies")
            self.assertTrue(by_alias["profile_dir"].endswith("/profiles/twitter_main"))


class SessionLaunchResolutionTest(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_profile_cookie_and_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BrowserSessionManager(state_root=tmpdir)
            await manager.set_launch_config(
                config_name="default",
                values={
                    "headless": True,
                    "profile": "social_media_main",
                    "start_url": "https://example.com/home",
                },
            )
            await manager.set_profile(
                profile="social_media_main",
                cookie_name="social_media_cookies",
                launch_overrides={"sandbox": False},
            )
            context = manager._resolve_launch_context(
                headless=None,
                start_url=None,
                user_data_dir=None,
                browser_args=None,
                browser_executable_path=None,
                sandbox=None,
                cookie_file=None,
                cookie_fallback_domain=None,
                profile=None,
                cookie_name=None,
                launch_config=None,
            )
            values = context["values"]
            self.assertTrue(values["headless"])
            self.assertFalse(values["sandbox"])
            self.assertEqual(values["profile"], "social_media_main")
            self.assertEqual(values["cookie_name"], "social_media_cookies")
            self.assertTrue(values["cookie_file"].endswith("/cookies/social_media_cookies.json"))
            self.assertTrue(values["user_data_dir"].endswith("/profiles/social_media_main"))

    async def test_explicit_values_override_saved_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BrowserSessionManager(state_root=tmpdir)
            await manager.set_launch_config(
                config_name="default",
                values={
                    "headless": True,
                    "sandbox": False,
                },
            )
            context = manager._resolve_launch_context(
                headless=False,
                start_url="https://custom.example",
                user_data_dir=None,
                browser_args=["--window-size=1280,720"],
                browser_executable_path=None,
                sandbox=True,
                cookie_file=None,
                cookie_fallback_domain=None,
                profile=None,
                cookie_name=None,
                launch_config=None,
            )
            values = context["values"]
            self.assertFalse(values["headless"])
            self.assertTrue(values["sandbox"])
            self.assertEqual(values["start_url"], "https://custom.example")
            self.assertEqual(values["browser_args"], ["--window-size=1280,720"])


if __name__ == "__main__":
    unittest.main()
