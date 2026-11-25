"""Deterministic tests (no AI calls). Run: .venv/bin/python -m unittest discover tests"""

import unittest

from app import describe_plan, describe_trip, normalize_sandbox, to_category_key, to_number


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


class CalendarHelpersTest(unittest.TestCase):
    """Calendar view (#6): AI replies are cleaned into numbers the budget can add up."""

    def test_to_number_reads_prices(self):
        self.assertEqual(to_number(40), 40)
        self.assertEqual(to_number("~$40"), 40)
        self.assertEqual(to_number("$1,200"), 1200)
        self.assertEqual(to_number("~$35-45/night"), 35)
        self.assertEqual(to_number("free"), 0)
        self.assertEqual(to_number(None), 0)

    def test_normalize_fills_defaults_and_coerces(self):
        raw = {"flights": {"route": "JFK-GUA", "est_cost": "~$500"},
               "legs": [{"name": "Antigua", "nightly": "~$40", "items": [
                   {"title": "Acatenango overnight", "kind": "Activity", "days": "2", "est_cost": "$100"},
                   {"title": "", "kind": "activity"},
                   {"title": "Mystery", "kind": "spaceship", "days": 99}]}]}
        out = normalize_sandbox(raw)
        self.assertEqual(out["flights"]["est_cost"], 500)
        self.assertEqual(out["food_per_day"], 0)
        leg = out["legs"][0]
        self.assertEqual(leg["nightly"], 40)
        self.assertEqual([i["title"] for i in leg["items"]], ["Acatenango overnight", "Mystery"])
        self.assertEqual(leg["items"][0]["kind"], "activity")
        self.assertEqual(leg["items"][0]["days"], 2)
        self.assertEqual(leg["items"][0]["est_cost"], 100)
        self.assertEqual(leg["items"][1]["kind"], "activity")  # unknown kind falls back
        self.assertEqual(leg["items"][1]["days"], 5)          # capped

    def test_normalize_handles_empty_reply(self):
        out = normalize_sandbox({})
        self.assertEqual(out["legs"], [])
        self.assertIsNone(out["flights"])

    def test_describe_plan_skips_blanks(self):
        text = describe_plan({"where": "Guatemala", "what": "  ", "budget": "~$1,200"})
        self.assertEqual(text, "- Where: Guatemala\n- Budget idea: ~$1,200")


if __name__ == "__main__":
    unittest.main()


class CalendarPagesTest(unittest.TestCase):
    def setUp(self):
        from app import app
        self.client = app.test_client()

    def test_pages_load(self):
        for url in ["/", "/step-by-step", "/calendar", "/calendar/start", "/research/where", "/research/budget"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_home_is_the_calendar_but_old_trip_links_still_work(self):
        self.assertIn(b"Trip calendar", self.client.get("/").data)
        self.assertNotIn(b"Trip calendar", self.client.get("/?trip=11111111-1111-1111-1111-111111111111").data)
        self.assertNotIn(b"Trip calendar", self.client.get("/step-by-step").data)

    def test_unknown_research_topic_is_404(self):
        self.assertEqual(self.client.get("/research/nope").status_code, 404)
        self.assertEqual(self.client.get("/research/<script>").status_code, 404)


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

    def test_calendar_sandbox_is_rate_limited(self):
        # Rule 8: every AI route shares the limit. A list body is invalid (400), so no AI call happens.
        codes = [self.client.post("/api/sandbox", json=[]).status_code for _ in range(15)]
        self.assertEqual(codes[:10], [400] * 10)
        self.assertEqual(codes[10:], [429] * 5)

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


class SavedTripsTest(unittest.TestCase):
    """Saved trips (Supabase). The database is faked, so no keys or network are needed."""

    TRIP_ID = "3f2b8c1e-4a5d-4e6f-9a7b-1c2d3e4f5a6b"

    def setUp(self):
        import app as app_module
        from unittest import mock
        app_module.limiter.reset()
        self.app_module = app_module
        self.client = app_module.app.test_client()
        self.patches = [mock.patch.object(app_module, "SUPABASE_URL", "https://dev.example.supabase.co"),
                        mock.patch.object(app_module, "SUPABASE_SECRET_KEY", "test-secret")]
        for p in self.patches:
            p.start()
        self.calls = []
        self.reply = []
        self.req = mock.patch.object(app_module.requests, "request", side_effect=self.fake_request)
        self.req.start()

    def tearDown(self):
        self.req.stop()
        for p in self.patches:
            p.stop()

    def fake_request(self, method, url, headers=None, params=None, json=None, timeout=None):
        from unittest import mock
        self.calls.append({"method": method, "url": url, "headers": headers, "params": params, "json": json})
        res = mock.Mock(content=b"x")
        res.json.return_value = self.reply
        res.raise_for_status.return_value = None
        return res

    def test_create_saves_only_known_fields_with_secret_key(self):
        self.reply = [{"id": self.TRIP_ID}]
        res = self.client.post("/api/trips", json={"trip": {"origin": "NYC", "decided": {"where": "Guatemala"}, "evil": 1}})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json(), {"id": self.TRIP_ID})
        call = self.calls[0]
        self.assertEqual(call["json"]["state"], {"origin": "NYC", "decided": {"where": "Guatemala"}})
        self.assertEqual(call["headers"]["apikey"], "test-secret")

    def test_load_returns_saved_trip(self):
        self.reply = [{"state": {"origin": "NYC"}}]
        res = self.client.get(f"/api/trips/{self.TRIP_ID}")
        self.assertEqual(res.get_json(), {"trip": {"origin": "NYC"}})
        self.assertEqual(self.calls[0]["params"]["id"], f"eq.{self.TRIP_ID}")

    def test_unknown_trip_is_404(self):
        self.reply = []
        self.assertEqual(self.client.get(f"/api/trips/{self.TRIP_ID}").status_code, 404)
        self.assertEqual(self.client.put(f"/api/trips/{self.TRIP_ID}", json={"trip": {}}).status_code, 404)

    def test_non_uuid_id_never_reaches_database(self):
        # e.g. trying to smuggle a PostgREST filter through the id
        for bad in ["1", "abc", "x,or=(id.neq.0)", "../trips"]:
            self.assertEqual(self.client.get(f"/api/trips/{bad}").status_code, 404, bad)
        self.assertEqual(self.calls, [])

    def test_missing_trip_is_400(self):
        self.assertEqual(self.client.post("/api/trips", json={"nope": 1}).status_code, 400)
        self.assertEqual(self.calls, [])

    def test_saving_off_without_keys(self):
        self.app_module.SUPABASE_SECRET_KEY = ""
        res = self.client.post("/api/trips", json={"trip": {}})
        self.assertEqual(res.status_code, 503)
        self.assertTrue(res.get_json()["saving_off"])

    def test_database_error_is_friendly_502(self):
        import requests
        self.req.stop()
        from unittest import mock
        self.req = mock.patch.object(self.app_module.requests, "request", side_effect=requests.ConnectionError("down"))
        self.req.start()
        res = self.client.put(f"/api/trips/{self.TRIP_ID}", json={"trip": {}})
        self.assertEqual(res.status_code, 502)
        self.assertNotIn("down", res.get_json()["error"])

    def test_trip_writes_are_rate_limited(self):
        self.reply = [{"id": self.TRIP_ID}]
        codes = [self.client.post("/api/trips", json={"trip": {}}).status_code for _ in range(40)]
        self.assertIn(429, codes)
        self.assertEqual(codes[-1], 429)


class PreviewUsesDevDatabaseTest(unittest.TestCase):
    """PR previews must never get the prod database keys."""

    def load_app_with(self, env):
        import importlib
        import os
        from unittest import mock
        import app as app_module
        with mock.patch.dict(os.environ, env, clear=False):
            return importlib.reload(app_module)

    def tearDown(self):
        import importlib
        import app as app_module
        importlib.reload(app_module)

    def test_preview_uses_dev_keys(self):
        env = {"IS_PULL_REQUEST": "true", "SUPABASE_URL": "https://prod.supabase.co", "SUPABASE_SECRET_KEY": "prod",
               "SUPABASE_DEV_URL": "https://dev.supabase.co", "SUPABASE_DEV_SECRET_KEY": "dev"}
        m = self.load_app_with(env)
        self.assertEqual((m.SUPABASE_URL, m.SUPABASE_SECRET_KEY), ("https://dev.supabase.co", "dev"))

    def test_preview_without_dev_keys_saves_nothing(self):
        env = {"IS_PULL_REQUEST": "true", "SUPABASE_URL": "https://prod.supabase.co", "SUPABASE_SECRET_KEY": "prod",
               "SUPABASE_DEV_URL": "", "SUPABASE_DEV_SECRET_KEY": ""}
        m = self.load_app_with(env)
        self.assertEqual(m.SUPABASE_SECRET_KEY, "")

    def test_production_uses_prod_keys(self):
        env = {"IS_PULL_REQUEST": "false", "SUPABASE_URL": "https://prod.supabase.co", "SUPABASE_SECRET_KEY": "prod"}
        self.assertEqual(self.load_app_with(env).SUPABASE_SECRET_KEY, "prod")
