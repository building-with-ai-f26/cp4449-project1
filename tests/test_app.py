"""Deterministic tests (no AI calls). Run: .venv/bin/python -m unittest discover tests"""

import unittest

from app import describe_trip, to_category_key


class DescribeTripTest(unittest.TestCase):
    """Per-decision preferences must reach the AI prompt."""

    def test_preferences_are_included(self):
        trip = {"decided": {"where": "Guatemala"}, "prefs": {"stay": "quiet area, kitchen"}}
        text = describe_trip(trip)
        self.assertIn("- Where (destination): Guatemala", text)
        self.assertIn("- Preferences for Accommodation: quiet area, kitchen", text)

    def test_blank_preferences_are_skipped(self):
        trip = {"decided": {"where": "Guatemala"}, "prefs": {"stay": "   "}}
        self.assertEqual(describe_trip(trip), "- Where (destination): Guatemala")

    def test_trip_without_prefs_still_works(self):
        # Older trip state (Build 1) has no "prefs" key at all.
        self.assertEqual(describe_trip({"origin": "NYC", "decided": {}}), "- Leaving from: NYC")


class CategoryKeyTest(unittest.TestCase):
    """The AI sometimes returns a category label instead of its key; the page needs the key."""

    def test_key_passes_through(self):
        self.assertEqual(to_category_key("when"), "when")

    def test_full_label_maps_to_key(self):
        self.assertEqual(to_category_key("When (dates / time of year)"), "when")
        self.assertEqual(to_category_key("Transportation"), "transport")
        self.assertEqual(to_category_key("Accommodation"), "stay")
        self.assertEqual(to_category_key("Cost / Budget"), "budget")

    def test_label_without_parentheses_maps_to_key(self):
        self.assertEqual(to_category_key("Where"), "where")


if __name__ == "__main__":
    unittest.main()
