"""Nextstop — Build 1 prototype.

A layered trip planner: the user enters what they know, picks one decision,
and the AI suggests options, compares the full picture, and suggests what to
decide next. The browser keeps the trip state; this server only calls the AI.

Run:  python3 app.py   then open http://localhost:5050
(Port 5050, because macOS AirPlay often uses 5000.)
"""

import json
import os

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

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
- Respect everything the traveler already knows or has locked in. Never contradict it.
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
    for key, label in CATEGORIES.items():
        value = (trip.get("decided") or {}).get(key)
        if value:
            lines.append(f"- {label}: {value}")
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


@app.route("/")
def home():
    return render_template("index.html", categories=CATEGORIES)


@app.post("/api/options")
def options():
    """Step 2: suggest 2-4 options for the chosen decision."""
    body = request.get_json()
    decide = CATEGORIES[body["decide"]]
    prompt = f"""The traveler's trip so far:
{describe_trip(body["trip"])}

They want to decide: {decide}

Suggest 3 strong options (4 at most) for this one decision. Return JSON:
{{"options": [{{
  "name": "short option name",
  "estimated_cost": "~$X total (or how this option affects cost)",
  "summary": "one line describing the option",
  "why_it_fits": "1-2 sentences tied to what the traveler said",
  "watch_out": "one specific non-obvious risk"
}}]}}"""
    return run(prompt)


@app.post("/api/compare")
def compare():
    """Step 3: show the full trip picture for 2-3 shortlisted options."""
    body = request.get_json()
    decide = CATEGORIES[body["decide"]]
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
what books up, what depends on what). Return JSON:
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
        return jsonify({"error": str(e)}), 500
    except Exception as e:  # keep the prototype simple: show the error on the page
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5050)
