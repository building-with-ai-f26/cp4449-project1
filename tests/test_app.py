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


class IdeasTest(unittest.TestCase):
    """First-page answers are starting ideas (#1): the AI must see them as not decided yet."""

    def test_idea_is_marked_not_decided(self):
        text = describe_trip({"ideas": {"when": "mid-April"}})
        self.assertIn("- Starting idea for When (dates / time of year) (not decided yet): mid-April", text)
        self.assertNotIn("- When (dates / time of year): mid-April", text)

    def test_locked_decision_replaces_idea(self):
        trip = {"ideas": {"when": "mid-April"}, "decided": {"when": "Apr 10-20"}}
        text = describe_trip(trip)
        self.assertIn("- When (dates / time of year): Apr 10-20", text)
        self.assertNotIn("mid-April", text)

    def test_preferences_replace_idea_for_same_category(self):
        # The preferences box is pre-filled from the idea, so the edited preferences win.
        trip = {"ideas": {"when": "mid-April"}, "prefs": {"when": "mid-April, avoid Semana Santa"}}
        text = describe_trip(trip)
        self.assertIn("- Preferences for When (dates / time of year): mid-April, avoid Semana Santa", text)
        self.assertNotIn("Starting idea", text)

    def test_blank_ideas_are_skipped(self):
        self.assertEqual(describe_trip({"ideas": {"when": "  "}}), "- Nothing yet")


class RetryTest(unittest.TestCase):
    """'Not quite right?' reruns: the AI must see what was ruled out and why."""

    def test_rejected_options_and_feedback_are_included(self):
        trip = {"rejected": {"where": {"options": ["Costa Rica", "Peru"], "feedback": ["too touristy"]}}}
        text = describe_trip(trip)
        self.assertIn("- Already ruled out for Where (destination): Costa Rica; Peru", text)
        self.assertIn("- What they didn't like about earlier Where (destination) options: too touristy", text)

    def test_rejections_ignored_once_category_is_locked(self):
        trip = {"decided": {"where": "Guatemala"}, "rejected": {"where": {"options": ["Peru"], "feedback": ["meh"]}}}
        self.assertEqual(describe_trip(trip), "- Where (destination): Guatemala")


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
