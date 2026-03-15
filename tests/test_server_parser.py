import unittest

from browser_bridge_mcp.server import build_parser


class ServerParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = build_parser()

    def test_defaults(self) -> None:
        args = self.parser.parse_args([])
        self.assertEqual(args.transport, "stdio")
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8000)
        self.assertEqual(args.log_level, "INFO")
        self.assertIsNone(args.state_root)

    def test_streamable_http_args(self) -> None:
        args = self.parser.parse_args(
            [
                "--transport",
                "streamable-http",
                "--host",
                "0.0.0.0",
                "--port",
                "8877",
                "--log-level",
                "DEBUG",
                "--state-root",
                "/tmp/browser-state",
            ]
        )
        self.assertEqual(args.transport, "streamable-http")
        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 8877)
        self.assertEqual(args.log_level, "DEBUG")
        self.assertEqual(args.state_root, "/tmp/browser-state")


if __name__ == "__main__":
    unittest.main()
