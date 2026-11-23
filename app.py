"""Nextstop — layered trip planner.

A layered trip planner: the user enters what they know, picks one decision,
and the AI suggests options, compares the full picture, and suggests what to
decide next. The browser keeps the trip state; this server only calls the AI.

Run:  python3 app.py   then open http://localhost:5050
(Port 5050, because macOS AirPlay often uses 5000.)
"""

import json
import os
import uuid
from datetime import datetime, timezone
from functools import wraps

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import BadRequest, NotFound
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()  # reads OPENROUTER_API_KEY (and optional OPENROUTER_MODEL) from .env

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-5.5")

CATEGORIES = {
    "where": "Where (destination)",
    "when": "When (dates / time of year)",
    "length": "Length of travel",
    "budget": "Cost / Budget",
    "transport": "Transportation",
    "stay": "Accommodation",
    "activities": "Top-level activities",
}

SYSTEM_PROMPT = """You are Nextstop, a travel-planning advisor. You help the traveler make ONE decision at a time.
Rules:
- Respect everything the traveler has locked in. Never contradict it.
- "Starting ideas (not decided yet)" are rough guidance, not final. Use them as a starting point.
- Match the layer: options are only as specific as what's already LOCKED allows. Planning goes big to small:
  destination first, then dates, then specific bookings. If Where isn't locked, When options are
  time-of-year windows (e.g. "early April", "mid-April", "late April"), never specific dates. Likewise, no named
  hotels, flights, or exact itineraries before the destination is locked.
- Every option must genuinely fit their stated budget and activities. If they say "cheap", only suggest
  options that are actually low-cost for them. Order options from best fit to worst fit.
- Be specific to THIS traveler: explain why an option fits what they said.
- Costs are rough estimates in USD for the whole trip per person, unless asked otherwise. Say "~" for estimates.
- "Watch out for" must be a specific, non-obvious risk the traveler probably didn't know to ask about
  (holidays or festivals that spike prices, rainy season, tight or delay-prone connections, long layovers
  that 'save' money, visa/entry rules, safety notes, booking-ahead needs). Never generic advice like "book early".
- Reply with valid JSON only, exactly matching the requested shape. No markdown, no extra text."""


def describe_trip(trip):
    """Turn the browser's trip state into plain text for the prompt."""
    lines = []
    if trip.get("origin"):
        lines.append(f"- Leaving from: {trip['origin']}")
    decided = trip.get("decided") or {}
    prefs = trip.get("prefs") or {}
    ideas = trip.get("ideas") or {}
    # Locked-in decisions: fixed facts the AI must respect.
    for key, label in CATEGORIES.items():
        value = decided.get(key)
        if value:
            lines.append(f"- {label}: {value}")
    # Starting ideas from the first page (e.g. "mid-April"): guidance, not decisions yet.
    # Skipped once the category is locked, or once preferences were given (that box is pre-filled from the idea).
    for key, label in CATEGORIES.items():
        idea = (ideas.get(key) or "").strip()
        if idea and not decided.get(key) and not (prefs.get(key) or "").strip():
            lines.append(f"- Starting idea for {label} (not decided yet): {idea}")
    # Preferences the traveler gave going into a specific decision (e.g. "quiet, kitchen" for Accommodation).
    for key, label in CATEGORIES.items():
        pref = (prefs.get(key) or "").strip()
        if pref:
            lines.append(f"- Preferences for {label}: {pref}")
    # "Not quite right?" reruns: options already shown and turned down, and why. Dropped once the category is locked.
    rejected = trip.get("rejected") or {}
    for key, label in CATEGORIES.items():
        r = rejected.get(key) or {}
        if decided.get(key):
            continue
        names = [n.strip() for n in r.get("options") or [] if n and n.strip()]
        feedback = [f.strip() for f in r.get("feedback") or [] if f and f.strip()]
        if names:
            lines.append(f"- Already ruled out for {label}: {'; '.join(names)}")
        if feedback:
            lines.append(f"- What they didn't like about earlier {label} options: {'; '.join(feedback)}")
    if trip.get("notes"):
        lines.append(f"- Other notes: {trip['notes']}")
    return "\n".join(lines) or "- Nothing yet"


def ask_ai(user_prompt, attempts=2):
    """Ask the AI, retrying once if the reply isn't valid JSON (long replies occasionally break)."""
    for attempt in range(attempts):
        try:
            return ask_ai_once(user_prompt)
        except json.JSONDecodeError:
            print(f"[ai] invalid JSON on attempt {attempt + 1}")
            if attempt == attempts - 1:
                raise


def ask_ai_once(user_prompt):
    """Send one prompt to OpenRouter and return the parsed JSON reply."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or "replace-with-your-key" in api_key:
        raise RuntimeError("OPENROUTER_API_KEY is missing. Add it to your .env file.")

    response = requests.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {api_key}", "X-Title": "Nextstop"},
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            # This model always "thinks" before answering, and that thinking counts toward max_tokens.
            # Low effort + a roomy limit keeps long replies (like compare) from getting cut off mid-JSON.
            "reasoning": {"effort": "low"},
            "max_tokens": 6000,
        },
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    text = data["choices"][0]["message"]["content"].strip()

    # Models sometimes wrap JSON in ```json fences; strip them before parsing.
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    # Keep only the JSON object, and allow raw newlines inside strings (strict=False).
    text = text[text.find("{"): text.rfind("}") + 1]
    result = json.loads(text, strict=False)

    usage = data.get("usage", {})
    print(f"[ai] {MODEL} tokens in={usage.get('prompt_tokens')} out={usage.get('completion_tokens')}")
    return result


app = Flask(__name__)
# Cap request size: every byte of the trip ends up in a paid AI prompt.
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024
# On Render a request passes visitor -> Cloudflare -> Render proxy -> app, so X-Forwarded-For arrives as
# "visitor, cloudflare, render". Trust exactly those 3 hops: the visitor is 3rd from the right, and anything a
# visitor fakes is added to the LEFT, so it can't change their rate-limit identity. (Verified on a PR preview.)
PROXY_HOPS = int(os.getenv("PROXY_HOPS", "3"))
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=PROXY_HOPS)

# Per-visitor (per-IP) limit on every route that calls the paid AI. In-memory storage is fine for one server process.
AI_LIMIT = os.getenv("AI_RATE_LIMIT", "10 per minute;60 per hour")
limiter = Limiter(get_remote_address, app=app, storage_uri="memory://")
# One shared budget across all AI routes, so a visitor can't get 10/min on each route separately.
ai_limit = limiter.shared_limit(AI_LIMIT, scope="ai")


@app.errorhandler(429)
def too_many_requests(e):
    return jsonify({"error": "You're going a bit fast. Please wait a minute and try again."}), 429


@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "That trip is too long to send. Try shortening your notes."}), 413


@app.errorhandler(BadRequest)
@app.errorhandler(KeyError)
@app.errorhandler(TypeError)
@app.errorhandler(AttributeError)
def bad_request(e):
    # Malformed or tampered request bodies get a 400, not a 500 with a stack trace.
    return jsonify({"error": "That request didn't look right. Reload the page and try again."}), 400


@app.route("/")
def home():
    # PostHog analytics (optional). The phc_ key is public, but we still keep config in .env.
    return render_template(
        "index.html",
        categories=CATEGORIES,
        posthog_key=os.getenv("POSTHOG_KEY", ""),
        posthog_host=os.getenv("POSTHOG_HOST", "https://us.i.posthog.com"),
    )


@app.post("/api/options")
@ai_limit
def options():
    """Step 2: suggest 2-4 options for the chosen decision."""
    body = request.get_json()
    decide = CATEGORIES[body["decide"]]
    prompt = f"""The traveler's trip so far:
{describe_trip(body["trip"])}

They want to decide: {decide}
If they gave "Preferences for {decide}", every option must respect them, and "why_it_fits" should say how.
Options must be distinct choices they could lock in at THIS layer (see "Match the layer"), not restatements of an idea.
If options were "Already ruled out", do not suggest them again, and use what they didn't like to suggest genuinely different ones.

Suggest 3 strong options (4 at most) for this one decision. Keep every bullet short (under ~15 words).
Return JSON:
{{"options": [{{
  "name": "short option name",
  "estimated_cost": "~$X-Y total (just the range)",
  "cost_breakdown": ["Flights ~$X", "Lodging ~$X (N nights at ~$X)", "Food ~$X", "..."],
  "trip_summary": [
    "Getting there: route and travel time",
    "Highlights: 2-3 specific places or hikes",
    "Where to stay: area and type",
    "A typical day: what you'd actually do",
    "Best time: within their dates if known"
  ],
  "why_it_fits": ["2-3 bullets, each tied to something the traveler said"],
  "watch_out": ["1-2 specific non-obvious risks"]
}}]}}"""
    return run(prompt)


@app.post("/api/compare")
@ai_limit
def compare():
    """Step 3: show the full trip picture for 2-3 shortlisted options."""
    body = request.get_json()
    decide = CATEGORIES[body["decide"]]
    if not isinstance(body["options"], list) or not 2 <= len(body["options"]) <= 3:
        raise BadRequest("Shortlist must have 2-3 options.")
    # Numbered list, not commas: option names can contain commas themselves.
    names = "".join(f"\n  {i + 1}. {name}" for i, name in enumerate(body["options"]))
    prompt = f"""The traveler's trip so far:
{describe_trip(body["trip"])}

They are deciding: {decide}. Shortlist ({len(body["options"])} options, in this order):{names}

Each row's "values" must have exactly {len(body["options"])} entries, one per option, in the order above.

Look ahead at the WHOLE trip each option would lead to, so they can decide with full information.
Fill in the rest of the trip (dates, flights, stay, activities, total cost) as you would recommend it.
Return JSON:
{{"columns": ["{body["options"][0]}", "..."],
  "rows": [
    {{"label": "Rough total cost", "values": ["...", "..."]}},
    {{"label": "Flights", "values": ["stops, total travel time, likely route", "..."]}},
    {{"label": "Best dates", "values": ["...", "..."]}},
    {{"label": "Activities fit", "values": ["...", "..."]}},
    {{"label": "Where to stay", "values": ["type and ~price per night", "..."]}},
    {{"label": "Watch out for", "values": ["...", "..."]}}
  ],
  "tradeoff": "2-3 sentences: the real trade-off between these options for THIS traveler (money vs time vs hassle vs fit)"}}"""
    return run(prompt)


@app.post("/api/next")
@ai_limit
def next_decision():
    """Step 4: suggest what to decide next. The traveler makes the final call."""
    body = request.get_json()
    open_keys = [k for k in CATEGORIES if not (body["trip"].get("decided") or {}).get(k)]
    if not open_keys:
        return jsonify({"suggestions": []})
    open_list = ", ".join(f"{k} ({CATEGORIES[k]})" for k in open_keys)
    prompt = f"""The traveler's trip so far:
{describe_trip(body["trip"])}

Still undecided: {open_list}

Rank the undecided categories by what they should decide next, and why (e.g. what drives cost,
what books up, what depends on what). Go big to small: the destination usually comes before dates, and dates
before specific bookings, since the later layers depend on it. Return JSON:
{{"suggestions": [{{"category": "the short key, e.g. \\"{open_keys[0]}\\"", "reason": "one sentence specific to this trip"}}]}}"""
    response = run(prompt)
    # The AI sometimes answers with the label ("When (dates...)") instead of the key ("when"). Map it back.
    data = response.get_json() if hasattr(response, "get_json") else None
    if data and "suggestions" in data:
        for s in data["suggestions"]:
            s["category"] = to_category_key(s.get("category", ""))
        return jsonify(data)
    return response


def to_category_key(value):
    """Turn 'when', 'When', or 'When (dates / time of year)' into 'when'."""
    value = value.strip().lower()
    for key, label in CATEGORIES.items():
        if value == key or value == label.lower() or value.startswith(label.lower().split(" (")[0].lower()):
            return key
    return value


def run(prompt):
    """Call the AI and turn any failure into a readable error for the page."""
    try:
        return jsonify(ask_ai(prompt))
    except json.JSONDecodeError:
        return jsonify({"error": "The AI returned something that wasn't valid JSON. Try again."}), 502
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 402:
            return jsonify({"error": "Your OpenRouter account is out of credits. Add credits at openrouter.ai/settings/credits."}), 402
        print(f"[ai] HTTP error: {e}")
        return jsonify({"error": "The AI service had a problem. Try again in a moment."}), 502
    except Exception as e:
        # Log the details on the server; don't show internals to visitors.
        print(f"[ai] error: {type(e).__name__}: {e}")
        return jsonify({"error": "Something went wrong on our side. Try again."}), 500


# ---------- Saved trips (Supabase, no sign-in) ----------
# The browser never talks to the database. Only this server does, with the secret key from .env / Render.
# Row Level Security is ON for the trips table with no policies, so the public key can't read or write anything.
# A trip is found by its random UUID, so the link is the only way to open it (like an unlisted doc).

# Render sets IS_PULL_REQUEST=true on PR preview deploys. Previews must never touch the prod database,
# so they use the DEV project's keys (SUPABASE_DEV_*), or save nothing if those aren't set.
IS_PREVIEW = os.getenv("IS_PULL_REQUEST") == "true"
SUPABASE_URL = os.getenv("SUPABASE_DEV_URL" if IS_PREVIEW else "SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_DEV_SECRET_KEY" if IS_PREVIEW else "SUPABASE_SECRET_KEY", "")
TRIP_LIMIT = os.getenv("TRIP_RATE_LIMIT", "30 per minute;500 per hour")
trip_limit = limiter.shared_limit(TRIP_LIMIT, scope="trips")
TRIP_KEYS = {"origin", "notes", "ideas", "decided", "prefs", "rejected"}


def db(method, params=None, body=None, prefer=None):
    """One call to the Supabase REST API for the trips table. Raises on HTTP errors."""
    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        raise RuntimeError("Saving is off: SUPABASE_URL / SUPABASE_SECRET_KEY are not set.")
    headers = {"apikey": SUPABASE_SECRET_KEY, "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    res = requests.request(method, f"{SUPABASE_URL}/rest/v1/trips", headers=headers,
                           params=params, json=body, timeout=10)
    res.raise_for_status()
    return res.json() if res.content else []


def trip_id_or_404(trip_id):
    """Only accept real UUIDs, so nothing else can reach the database query."""
    try:
        return str(uuid.UUID(trip_id))
    except ValueError:
        raise NotFound()


def clean_trip(body):
    """Keep only the trip fields the page uses. Anything else in the request is dropped."""
    trip = (body or {}).get("trip")
    if not isinstance(trip, dict):
        raise BadRequest("Missing trip.")
    return {k: v for k, v in trip.items() if k in TRIP_KEYS}


def saving(fn):
    """Turn database problems into friendly JSON errors (and keep details in the server log)."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except RuntimeError as e:
            return jsonify({"error": str(e), "saving_off": True}), 503
        except requests.RequestException as e:
            print(f"[db] error: {type(e).__name__}: {e}")
            return jsonify({"error": "Couldn't save your trip right now. Your work is still on this page."}), 502
    return wrapper


@app.post("/api/trips")
@trip_limit
@saving
def create_trip():
    rows = db("POST", body={"state": clean_trip(request.get_json())}, prefer="return=representation")
    return jsonify({"id": rows[0]["id"]}), 201


@app.get("/api/trips/<trip_id>")
@trip_limit
@saving
def load_trip(trip_id):
    rows = db("GET", params={"id": f"eq.{trip_id_or_404(trip_id)}", "select": "state"})
    if not rows:
        raise NotFound()
    return jsonify({"trip": rows[0]["state"]})


@app.put("/api/trips/<trip_id>")
@trip_limit
@saving
def save_trip(trip_id):
    rows = db("PATCH", params={"id": f"eq.{trip_id_or_404(trip_id)}", "select": "id"},
              body={"state": clean_trip(request.get_json()), "updated_at": datetime.now(timezone.utc).isoformat()},
              prefer="return=representation")
    if not rows:  # no trip with that id: don't pretend it saved
        raise NotFound()
    return jsonify({"ok": True})


@app.errorhandler(NotFound)
def not_found(e):
    return jsonify({"error": "Not found."}), 404


if __name__ == "__main__":
    # Debug mode shows an interactive debugger on errors. Never expose it on a shared link.
    # Turn it on locally only:  FLASK_DEBUG=1 .venv/bin/python app.py
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", port=5050)
