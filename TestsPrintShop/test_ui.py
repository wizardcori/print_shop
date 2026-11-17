"""UI rule tests independent from the PySide6 event loop."""

import unittest


def visible_tabs(tabs, completed_only):
    """Apply the documented tab visibility rule to simple test data."""
    if completed_only:
        return list(tabs)
    return [tab for tab in tabs if any(not row["completed"] for row in tab["rows"])]


def control_enabled(record):
    return record["file_exists"] and record["size_matches"]


class TestUiRules(unittest.TestCase):
    def test_completed_filter_shows_all_matching_tabs(self):
        """The completed filter must show both completed and incomplete tabs."""
        tabs = [{"name": "A", "rows": [{"completed": True}]},
                {"name": "B", "rows": [{"completed": False}]}]
        self.assertEqual([tab["name"] for tab in visible_tabs(tabs, True)], ["A", "B"])

    def test_default_filter_hides_completed_only_tabs(self):
        """Without the filter, tabs containing only completed rows are hidden."""
        tabs = [{"name": "A", "rows": [{"completed": True}]},
                {"name": "B", "rows": [{"completed": False}]}]
        self.assertEqual([tab["name"] for tab in visible_tabs(tabs, False)], ["B"])

    def test_invalid_file_disables_controls(self):
        """Missing or mismatched files must disable copy, color, and completion controls."""
        self.assertTrue(control_enabled({"file_exists": True, "size_matches": True}))
        self.assertFalse(control_enabled({"file_exists": False, "size_matches": True}))
        self.assertFalse(control_enabled({"file_exists": True, "size_matches": False}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
