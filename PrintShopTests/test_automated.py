"""Automated checks for the PrintShop test assistant."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import test_assistant  # noqa: E402


class TestAssistant(unittest.TestCase):
    def test_http_check_reports_success(self):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        with patch.object(test_assistant.urllib.request, "urlopen", return_value=Response()):
            self.assertEqual(test_assistant.check_http("http://example.test/scan"),
                             (200, "HTTP endpoint is reachable"))

    def test_automatic_checks_return_standard_records(self):
        class FakeSocket:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        with patch.object(test_assistant.socket, "create_connection", return_value=FakeSocket()), \
                patch.object(test_assistant, "check_http",
                             return_value=(200, "HTTP endpoint is reachable")):
            checks = test_assistant.run_automatic_checks("127.0.0.1", 5000)
        self.assertEqual([item["result"] for item in checks[:2]], ["PASS", "PASS"])
        self.assertGreaterEqual(len(checks), 7)
        self.assertTrue(all({"step", "note", "result", "expected", "actual"} <= item.keys()
                            for item in checks))

    def test_saved_result_file_has_expected_schema(self):
        result_files = sorted((ROOT / "results").glob("*.json"))
        self.assertTrue(result_files, "No saved test result JSON was found")
        data = json.loads(result_files[-1].read_text(encoding="utf-8"))
        self.assertIn("started", data)
        self.assertIsInstance(data["results"], list)
        self.assertTrue(all(item["result"] in {"PASS", "FAIL"} for item in data["results"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
