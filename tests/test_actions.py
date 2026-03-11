import unittest

from browser_bridge_mcp.actions import normalize_evaluate_payload


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


if __name__ == "__main__":
    unittest.main()
