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
        """Verify that a reachable HTTP endpoint returns status 200."""
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        # Replace the network call with a deterministic successful response.
        with patch.object(test_assistant.urllib.request, "urlopen", return_value=Response()):
            # The helper should convert the HTTP response into the expected tuple.
            self.assertEqual(test_assistant.check_http("http://example.test/scan"),
                             (200, "HTTP endpoint is reachable"))

    def test_automatic_checks_return_standard_records(self):
        """Verify automatic checks produce complete, consistently shaped records."""
        class FakeSocket:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        # Mock TCP and HTTP so this unit test does not depend on a live hotspot.
        with patch.object(test_assistant.socket, "create_connection", return_value=FakeSocket()), \
                patch.object(test_assistant, "check_http",
                             return_value=(200, "HTTP endpoint is reachable")):
            checks = test_assistant.run_automatic_checks("127.0.0.1", 5000)
        # The first two checks must pass: TCP connectivity and the QR web endpoint.
        self.assertEqual([item["result"] for item in checks[:2]], ["PASS", "PASS"])
        # Additional checks cover hotspot configuration, DB, files, sync, and admin records.
        self.assertGreaterEqual(len(checks), 7)
        # Every result must expose the fields used by the JSON report.
        self.assertTrue(all({"step", "note", "result", "expected", "actual"} <= item.keys()
                            for item in checks))

    def test_saved_result_file_has_expected_schema(self):
        """Verify the latest saved report contains the required JSON structure."""
        result_files = sorted((ROOT / "results").glob("*.json"))
        # At least one previous assistant run is required for this report test.
        self.assertTrue(result_files, "No saved test result JSON was found")
        data = json.loads(result_files[-1].read_text(encoding="utf-8"))
        # Validate the top-level timestamp and result collection.
        self.assertIn("started", data)
        self.assertIsInstance(data["results"], list)
        # Each test result must use the supported PASS/FAIL values.
        self.assertTrue(all(item["result"] in {"PASS", "FAIL"} for item in data["results"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
