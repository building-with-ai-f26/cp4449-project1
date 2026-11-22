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


class SecurityTest(unittest.TestCase):
    """Build 3 hardening. These send bad bodies, so no AI call (and no cost) ever happens."""

    def setUp(self):
        from app import app, limiter
        limiter.reset()
        self.client = app.test_client()

    def test_rate_limit_returns_429(self):
        # Same check as the live audit: 30 calls in a row must start returning 429.
        codes = [self.client.post("/api/options", json={}).status_code for _ in range(30)]
        self.assertIn(429, codes)
        self.assertEqual(codes[-1], 429)
        self.assertIn("error", self.client.post("/api/options", json={}).get_json())

    def test_each_visitor_has_their_own_limit(self):
        for _ in range(30):
            self.client.post("/api/next", json={}, environ_base={"REMOTE_ADDR": "1.1.1.1"})
        other = self.client.post("/api/next", json={}, environ_base={"REMOTE_ADDR": "2.2.2.2"})
        self.assertNotEqual(other.status_code, 429)

    def test_malformed_body_is_400_not_500(self):
        for body in [{}, {"decide": "nope", "trip": {}}, {"trip": "x"}, []]:
            res = self.client.post("/api/options", json=body)
            self.assertEqual(res.status_code, 400, body)

    def test_compare_rejects_huge_shortlist(self):
        res = self.client.post("/api/compare", json={"decide": "where", "trip": {}, "options": ["a"] * 50})
        self.assertEqual(res.status_code, 400)

    def test_oversized_request_is_rejected(self):
        res = self.client.post("/api/options", json={"decide": "where", "trip": {"notes": "x" * 50000}})
        self.assertEqual(res.status_code, 413)


class ProxyRateLimitTest(unittest.TestCase):
    """Regression: on Render, X-Forwarded-For is 'visitor, cloudflare, render'. The limit must key on the visitor."""

    def setUp(self):
        from app import app, limiter
        limiter.reset()
        self.client = app.test_client()

    def hit(self, path, xff):
        return self.client.post(path, json={}, headers={"X-Forwarded-For": xff}).status_code

    def test_limit_holds_when_cloudflare_and_render_hops_change(self):
        # Same visitor, but every request arrives through a different Cloudflare edge and Render proxy (the live bug).
        codes = [self.hit("/api/options", f"108.41.128.146, 104.22.72.{i}, 10.28.0.{i}") for i in range(30)]
        self.assertEqual(codes[10:], [429] * 20)

    def test_spoofed_header_cannot_dodge_limit(self):
        # A visitor sending their own X-Forwarded-For only adds entries on the left.
        codes = [self.hit("/api/options", f"6.6.6.{i}, 108.41.128.146, 104.22.72.1, 10.28.0.1") for i in range(30)]
        self.assertEqual(codes[-1], 429)

    def test_limit_is_shared_across_ai_routes(self):
        xff = "5.5.5.5, 104.22.72.1, 10.28.0.1"
        codes = [self.hit(p, xff) for p in ["/api/options", "/api/compare", "/api/next"] * 5]
        self.assertEqual(codes[10:], [429] * 5)

    def test_different_visitors_have_separate_limits(self):
        for _ in range(15):
            self.hit("/api/next", "1.1.1.1, 104.22.72.1, 10.28.0.1")
        self.assertNotEqual(self.hit("/api/next", "2.2.2.2, 104.22.72.1, 10.28.0.1"), 429)
