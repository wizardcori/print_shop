"""File transfer rule tests for visibility, synchronization, and validation."""

import tempfile
import unittest
from pathlib import Path


def is_summary(filename):
    return filename.startswith("summary_") or filename == "transfer_summary.txt"


def file_matches(folder, record):
    path = Path(folder) / record["filename"]
    return path.is_file() and path.stat().st_size == record["bytes"]


def should_sync(folder, record):
    return not is_summary(record["filename"]) and file_matches(folder, record)


class TestTransferRules(unittest.TestCase):
    def test_summary_files_are_not_synced(self):
        """Summary files must never be sent to the user screen."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "summary_20261017.txt"
            path.write_text("summary", encoding="utf-8")
            self.assertFalse(should_sync(folder, {"filename": path.name, "bytes": 7}))

    def test_matching_file_is_synced(self):
        """A real file with the persisted byte size is eligible for sync."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.pdf"
            path.write_bytes(b"1234")
            self.assertTrue(should_sync(folder, {"filename": path.name, "bytes": 4}))

    def test_missing_or_mismatched_file_is_not_synced(self):
        """Missing and size-mismatched files must remain out of user sync."""
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(should_sync(folder, {"filename": "missing.pdf", "bytes": 4}))
            path = Path(folder) / "wrong.pdf"
            path.write_bytes(b"123")
            self.assertFalse(should_sync(folder, {"filename": path.name, "bytes": 4}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
