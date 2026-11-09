"""Deterministic tests (no AI calls). Run: .venv/bin/python -m unittest discover tests"""

import unittest

from app import to_category_key


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
