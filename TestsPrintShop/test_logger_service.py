"""Tests for the common queued logging system with feature directories and tagged filenames."""

import datetime
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_APP = ROOT.parent / "PrintShopApp"
sys.path.insert(0, str(PROJECT_APP))

from Common.logger_service import (
    CommonQueuedBatchFileHandler,
    TaggedFormatter,
    get_dated_log_filename,
    get_feature_log_dir,
    get_feature_logger,
    log_event,
    flush_all_loggers,
)


class TestLoggerService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        flush_all_loggers()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_dated_log_filename_format(self):
        """Verify filename adheres to 20261011_XXX.LOG format."""
        fn = get_dated_log_filename("WIFI", "20261011")
        self.assertEqual(fn, "20261011_WIFI.LOG")

        fn2 = get_dated_log_filename("security")
        today = datetime.datetime.now().strftime("%Y%m%d")
        self.assertEqual(fn2, f"{today}_SECURITY.LOG")

    def test_feature_log_dir_partitioning(self):
        """Verify log directory is partitioned by feature name."""
        hotspot_dir = get_feature_log_dir("Hotspot", self.temp_dir)
        self.assertTrue(os.path.isdir(hotspot_dir))
        self.assertTrue(hotspot_dir.endswith("hotspot"))

    def test_queued_logging_and_tags(self):
        """Verify log records are written via queue with [TAG] header."""
        logger = get_feature_logger(
            feature="test_feat",
            tag="UNIT_TEST",
            base_dir=self.temp_dir,
            flush_interval=0.1,
        )
        logger.info("Hello from unit test!")
        time.sleep(0.3)
        flush_all_loggers()

        target_dir = os.path.join(self.temp_dir, "test_feat")
        today = datetime.datetime.now().strftime("%Y%m%d")
        expected_file = os.path.join(target_dir, f"{today}_UNIT_TEST.LOG")
        self.assertTrue(os.path.exists(expected_file))

        with open(expected_file, "r", encoding="utf-8") as stream:
            content = stream.read()
        self.assertIn("[INFO]", content)
        self.assertIn("[UNIT_TEST]", content)
        self.assertIn("Hello from unit test!", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
