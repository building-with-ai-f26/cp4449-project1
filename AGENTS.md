# AGENTS.md — Coding Agent Operating Manual

> Give this file to your coding agent and check that it is using these instructions. Keep the stack, commands, and ground rules current.

## 1. Project Overview
- **What this repo builds:** Nextstop, a layered trip planner. You enter what you know, pick one decision, and AI suggests options with trade-offs and "watch out for" warnings, compares the full trip for a shortlist, and suggests what to decide next (the user always chooses).
- **Primary user & core workflow:** [See the living PRD in `docs/index.html`]
- **Tech stack:** Python 3.12 / Flask / vanilla HTML+JS (`templates/index.html`) / OpenRouter API (default model `anthropic/claude-sonnet-5.5`). Trip state lives in the browser and is autosaved to Supabase (Postgres) through the server. No sign-in: a trip is opened by its private random-UUID link. Hosted on Render (free web service, gunicorn).
- **Live URL:** https://nextstop-x4bo.onrender.com

## 2. Commands
- **Install dependencies:** `uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -r requirements.txt` (or `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt`), then `cp .env.example .env` and add your OpenRouter key (and optionally your PostHog `phc_` key)
- **Run locally:** `.venv/bin/python app.py`, then open http://localhost:5050
- **Run deterministic tests:** `.venv/bin/python -m unittest discover tests`
- **Run dependency audit:** `.venv/bin/pip-audit -r requirements.txt`
- **Run production server locally:** `.venv/bin/gunicorn app:app --workers 1 --threads 4 --timeout 120 --bind 127.0.0.1:5050`
- **Run model evals:** Not yet (planned for Build 4)
- **Debug mode (local only):** `FLASK_DEBUG=1 .venv/bin/python app.py`. Off by default, because the debugger lets anyone who reaches the server run code.

### Environment variables (`.env`, git-ignored; template in `.env.example`)
| Variable | Required | What it does |
| :--- | :--- | :--- |
| `OPENROUTER_API_KEY` | Yes | Secret. Used only by `app.py` on the server, never sent to the browser. |
| `OPENROUTER_MODEL` | No | Defaults to `anthropic/claude-sonnet-5.5`. |
| `POSTHOG_KEY` | No | Public `phc_` key. If blank, the local app loads no analytics. |
| `POSTHOG_HOST` | No | Defaults to `https://us.i.posthog.com`. |
| `SUPABASE_URL` | No | Supabase project URL. **Local = dev project, Render = prod project.** Blank = saving off. |
| `SUPABASE_SECRET_KEY` | No | Secret (`sb_secret_…`). Server only; bypasses RLS. Never in the browser, git, or chat. |
| `SUPABASE_DEV_URL` / `SUPABASE_DEV_SECRET_KEY` | Render only | Dev project keys used by **PR previews** (Render sets `IS_PULL_REQUEST=true`), so previews never touch prod. |
| `TRIP_RATE_LIMIT` | No | Per-visitor limit on trip load/save. Defaults to `30 per minute;500 per hour`. |
| `AI_RATE_LIMIT` | No | Per-visitor limit on AI routes. Defaults to `10 per minute;60 per hour`. |
| `PROXY_HOPS` | No | Proxies in front of the app (Cloudflare + Render = 3). Only change if Render changes its setup. |

## 2b. Project Structure
```
app.py                 Flask server: prompts, OpenRouter calls, JSON cleanup. 3 API routes:
                         POST /api/options  → 3–4 options for one decision (respects per-decision preferences)
                         POST /api/compare  → full-trip comparison table for a 2–3 option shortlist
                         POST /api/next     → ranks which undecided category to decide next
                       + 3 trip routes (Supabase via REST, secret key, server only):
                         POST /api/trips → create, GET/PUT /api/trips/<uuid> → load/save
templates/index.html   The whole app UI (vanilla HTML/JS). Holds trip state in the browser:
                         { origin, notes, decided: {category: choice}, prefs: {category: preferences} }
                         Screens: Knowns → Preferences → Options → Compare → What's next → Done
tests/test_app.py      Deterministic unit tests (no AI calls): describe_trip(), to_category_key()
supabase/migrations/   SQL schema changes, numbered (0001_create_trips.sql). The only way the schema changes
scripts/backup.py      Exports all trips to backups/ (git-ignored). Run before touching prod
render.yaml            Render Blueprint: build/start commands, auto-deploy after checks, PR previews, env vars
.github/workflows/     checks.yml: unit/security tests, pip-audit, secret scan on every PR and push to main
SECURITY.md            Security audit results (Build 3)
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
7. **Never turn on debug mode outside your own machine.** (Real mistake: an earlier agent session ran the app with `debug=True` hard-coded, which exposes Flask's interactive debugger, letting anyone who reaches the server run code. Fixed in commit "Turn off Flask debug mode unless FLASK_DEBUG=1".) Never set `FLASK_DEBUG` on Render, never pass `debug=True` in code, and production always runs through gunicorn, never `python app.py`.
8. **Every route that calls the AI gets `@ai_limit` (one shared per-visitor budget)** and a test proving it returns 429.

9. **Databases: the agent works only against DEV.** Your local `.env` points at `nextstop-dev`; only Render has prod keys. Never put prod keys in `.env`, run SQL on prod, or run `scripts/backup.py` against prod without asking.
10. **Schema changes only via a new numbered file in `supabase/migrations/`** (never edit an old one). Apply to dev in the Supabase SQL Editor, test, and get the human's OK before it is applied to prod. Every new table must `enable row level security`.
11. **The browser never talks to Supabase.** All reads and writes go through Flask routes with a rate limit. No Supabase keys in `templates/`.

## 4. Ask Me First (stop and get explicit human approval)
- **Deleting or changing data / databases:** applying a migration to prod, any SQL on prod, deleting rows, `git push --force`, `git reset --hard`, deleting branches, deleting Render services or deploys, adding a database or changing schema.
- **Keys, secrets, permissions:** creating, viewing, rotating or changing any API key or env var on Render/OpenRouter/PostHog; changing GitHub repo settings, branch protection, collaborators or Actions permissions.
- **Anything that costs money:** changing the Render plan, OpenRouter credits/spend cap, switching to a pricier model, raising `AI_RATE_LIMIT`, or running more than a handful of live AI calls (each costs real credits).
- **Merging to `main`** (it deploys to production) and **rolling back** production.

## 5. Shipping (agent follows these steps; stop at any Ask Me First item)
0. **If the PR has a migration:** apply it to dev and test locally first. Before merging, the human backs up prod (`scripts/backup.py` with prod values), then applies the migration in prod's SQL Editor, *then* merges. The schema must exist before the code that uses it.
1. **Branch:** `git checkout main && git pull && git checkout -b <short-topic>`. Never commit straight to `main`.
2. **Change + check locally:** make the small change, run `.venv/bin/python -m unittest discover tests` and `.venv/bin/pip-audit -r requirements.txt`. Both must pass.
3. **Pull request:** `git push -u origin <branch>` then `gh pr create --fill` and fill in the PR template.
4. **Checks:** `gh pr checks --watch`. GitHub Actions (`checks.yml`) runs tests, pip-audit and the secret scan. If they fail, fix and push; don't merge red.
5. **Preview:** Render posts a preview URL on the PR (`nextstop-pr-<N>.onrender.com`). Open it and run the core workflow once (Knowns → Options → Compare → What's next).
6. **Merge (Ask me first):** after the human says yes, `gh pr merge --squash --delete-branch`.
7. **Deploy:** Render auto-deploys `main` once checks pass (`autoDeployTrigger: checksPass`). Watch it in the Render dashboard → Events.
8. **Verify live:** `curl -s -o /dev/null -w "%{http_code}" https://nextstop-x4bo.onrender.com/` returns 200, then click through the core workflow on the live site and confirm PostHog shows the pageview.
9. **Rollback if broken (Ask me first):** fastest is Render dashboard → Events → pick the last good deploy → **Rollback**. Then fix forward with `git revert <bad-sha>` in a new PR so `main` matches what's live. **Rolling back turns off Render's auto-deploy.** Afterwards, go to Settings → Build & Deploy → Auto-Deploy and set it back to "After CI checks pass", or merges will stop deploying. (Tested Nov 22.)

> Free-tier note: the Render service sleeps after ~15 min idle; the first visit can take ~30-60s to wake up.
