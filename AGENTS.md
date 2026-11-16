# AGENTS.md — Coding Agent Operating Manual

> Give this file to your coding agent and check that it is using these instructions. Keep the stack, commands, and ground rules current.

## 1. Project Overview
- **What this repo builds:** Nextstop, a layered trip planner. You enter what you know, pick one decision, and AI suggests options with trade-offs and "watch out for" warnings, compares the full trip for a shortlist, and suggests what to decide next (the user always chooses).
- **Primary user & core workflow:** [See the living PRD in `docs/index.html`]
- **Tech stack:** Python 3.9+ / Flask / vanilla HTML+JS (`templates/index.html`) / OpenRouter API (default model `anthropic/claude-sonnet-5.5`). Trip state lives in the browser; no database.

## 2. Commands
- **Install dependencies:** `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, then `cp .env.example .env` and add your OpenRouter key (and optionally your PostHog `phc_` key)
- **Run locally:** `.venv/bin/python app.py`, then open http://localhost:5050
- **Run deterministic tests:** `.venv/bin/python -m unittest discover tests`
- **Run model evals:** Not yet (planned for Build 4)
- **Debug mode (local only):** `FLASK_DEBUG=1 .venv/bin/python app.py`. Off by default, because the debugger lets anyone who reaches the server run code.

### Environment variables (`.env`, git-ignored; template in `.env.example`)
| Variable | Required | What it does |
| :--- | :--- | :--- |
| `OPENROUTER_API_KEY` | Yes | Secret. Used only by `app.py` on the server, never sent to the browser. |
| `OPENROUTER_MODEL` | No | Defaults to `anthropic/claude-sonnet-5.5`. |
| `POSTHOG_KEY` | No | Public `phc_` key. If blank, the local app loads no analytics. |
| `POSTHOG_HOST` | No | Defaults to `https://us.i.posthog.com`. |

## 2b. Project Structure
```
app.py                 Flask server: prompts, OpenRouter calls, JSON cleanup. 3 API routes:
                         POST /api/options  → 3–4 options for one decision (respects per-decision preferences)
                         POST /api/compare  → full-trip comparison table for a 2–3 option shortlist
                         POST /api/next     → ranks which undecided category to decide next
templates/index.html   The whole app UI (vanilla HTML/JS). Holds trip state in the browser:
                         { origin, notes, decided: {category: choice}, prefs: {category: preferences} }
                         Screens: Knowns → Preferences → Options → Compare → What's next → Done
tests/test_app.py      Deterministic unit tests (no AI calls): describe_trip(), to_category_key()
docs/index.html        Product Page + living PRD + build log, served by GitHub Pages from /docs
docs/images/           Screenshots and workflow diagrams used on the Product Page
journal/, Plan.md      Optional course scratch notes (not the source of truth; docs/index.html is)
```
**Data flow for one action:** browser sends `trip` + the decision → `app.py` turns it into text with `describe_trip()` → OpenRouter → JSON reply is cleaned, parsed (one retry on bad JSON) → page renders cards/table. No database; nothing is stored server-side.

**Analytics:** PostHog (pageviews, autocapture clicks, session replay) runs on both the local app and the Product Page.

## 3. Non-Negotiable Engineering Rules
1. **Plan before coding:** Before touching multiple files, propose a brief plan and wait for approval.
2. **Small batches:** Make small, focused changes that can be reviewed and explained by a human in a single Pull Request.
3. **Explainability:** Avoid unnecessary abstractions or dependencies. Help the human builder understand the main components, what changed, why it matters, what could break, and how it was checked.
4. **Verify changes:** Run relevant checks. For a reproducible logic bug, use a failing test to demonstrate the fix when practical. Record manual checks and known limitations; follow the selected Build 4 evaluation track.
5. **Zero secrets in code:** Never hardcode API keys, tokens, or credentials. Always read from environment variables (`.env`) and update `.env.example` when new variables are needed.
6. **Stop when looping:** If a fix fails twice in a row, stop, summarize what failed, and ask the human before trying a third approach.
