"""HTTP contract tests that do not require a running server or a phone."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import test_assistant  # noqa: E402


class TestApiContracts(unittest.TestCase):
    def test_required_routes_are_checked(self):
        """The assistant must check the QR and transfer-status endpoints."""
        with patch.object(test_assistant.socket, "create_connection"), \
                patch.object(test_assistant, "check_http", return_value=(200, "ok")), \
                patch.object(test_assistant, "check_hotspot_config",
                             return_value={"step": "Hotspot SSID and IP", "note": "ok", "result": "PASS"}), \
                patch.object(test_assistant, "check_database",
                             return_value={"step": "DB storage", "note": "ok", "result": "PASS"}), \
                patch.object(test_assistant, "check_transfer_files",
                             return_value={"step": "File existence and size", "note": "ok", "result": "PASS"}), \
                patch.object(test_assistant, "check_sync_endpoint",
                             return_value={"step": "User synchronization data", "note": "ok", "result": "PASS"}), \
                patch.object(test_assistant, "check_admin_records",
                             return_value={"step": "Administrator record", "note": "ok", "result": "PASS"}):
            steps = {item["step"] for item in test_assistant.run_automatic_checks("127.0.0.1")}
        self.assertIn("QR web endpoint", steps)
        self.assertIn("User synchronization data", steps)

    def test_http_failure_is_reported(self):
        """Connection errors must become a FAIL result instead of an exception."""
        with patch.object(test_assistant.urllib.request, "urlopen",
                          side_effect=OSError("connection refused")):
            status, note = test_assistant.check_http("http://127.0.0.1:9/scan")
        self.assertIsNone(status)
        self.assertIn("connection refused", note)


if __name__ == "__main__":
    unittest.main(verbosity=2)
