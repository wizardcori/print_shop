"""Database persistence tests using an isolated temporary SQLite database."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "PrintShopApp"))
from db import AppDatabase  # noqa: E402


class TestDatabase(unittest.TestCase):
    def setUp(self):
        # SQLite may briefly retain a Windows file handle after a context exits.
        # Ignore cleanup errors because this is an isolated disposable test folder.
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.database = AppDatabase(str(Path(self.temp_dir.name) / "test.db"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_transfer_log_round_trip(self):
        """A transfer record must survive save and reload."""
        record = {"filename": "sample.pdf", "size": "1.0 KB",
                  "copies": 2, "color": "Color", "received_time": "20261017_101109"}
        self.database.save_transfer_log("folder-a", "client-a", record)
        loaded = self.database.load_transfer_logs()
        self.assertEqual(loaded[("folder-a", "client-a")][0], record)

    def test_transfer_updates_persist(self):
        """Copy count, color, and completion status must be persisted."""
        record = {"filename": "sample.pdf", "size": "1.0 KB", "copies": 1,
                  "color": "Color", "received_time": "20261017_101109"}
        self.database.save_transfer_log("folder-a", "client-a", record)
        self.database.update_transfer_log("folder-a", "sample.pdf", copies=4, color="B&W")
        self.database.update_transfer_completed("folder-a", "sample.pdf", True)
        data = self.database.load_transfer_logs()[("folder-a", "client-a")][0]
        self.assertEqual((data["copies"], data["color"], data["task_completed"]),
                         (4, "B&W", True))

    def test_required_tables_are_created(self):
        """Database initialization must create all application tables."""
        import sqlite3
        with sqlite3.connect(self.database.path) as connection:
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"sessions", "usage_events", "file_transfers", "transfer_log"} <= tables)


if __name__ == "__main__":
    unittest.main(verbosity=2)
