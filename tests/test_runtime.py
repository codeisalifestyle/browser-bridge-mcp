import json
import tempfile
import unittest
from pathlib import Path

from browser_bridge_mcp.runtime import resolve_connection


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


if __name__ == "__main__":
    unittest.main()
