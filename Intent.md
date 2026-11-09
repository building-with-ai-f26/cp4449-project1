# Intent.md — Optional PRD Draft (Build 1)

Use this as a scratchpad if helpful. Publish the required PRD and Build 1 log on `docs/index.html`; this file is not a separate hand-in.

**Build 1 due:** Monday, Nov 9, 2026 at noon, New York time  
**Builder:** Caroline Paul  
**Product:** Nextstop (working name)

---

## 1. Who is it for?
*Name a specific person or role you have direct access to (not a broad demographic). Who will actually test and use this before Demo Day?*

- **Target user:** Me — someone who loves planning trips (solo and with groups) and is usually the one doing the planning. Later: friends I plan group trips with.
- **How I will reach them to test it:** I am the first user (replaying my real Guatemala trip). Then my friends, who I can text directly, for solo and group testing.

## 2. What job does it do?
*Describe the concrete recurring problem from work, school, or life, and what "done" looks like for the user.*

- **Current painful workflow (before):** Planning my solo Guatemala trip, I started with what I knew (10 free days between quitting my job and leaving for Europe, wanting moderate hiking / first-time backpacking, wanting it cheap). Then I had to compare Guatemala, Colombia, Costa Rica, and the Dolomites across dozens of tabs, then figure out dates by digging through airlines, airports, and connections. "Cheapest" isn't "best" — once I flew London → NY through Lisbon to save $200 and it added ~5 hours I didn't see coming. One-prompt AI planners skip all of this and hand you a full itinerary you didn't actually decide.
- **New workflow with this product (after):** A layered planner. I enter my **knowns**, choose **what I want to decide first**, and the AI gives 2–4 options with why each fits me and the hidden trade-offs. Before committing, I can **shortlist 2–3 options and see the full picture** of each (rough cost, flights, best dates, activities, lodging) side by side. I lock a decision, the AI **suggests what to decide next** (I make the final call), and I repeat until the trip is planned.
- **Why this is useful** *(used weekly / saves real time / worth paying for)*: I plan several trips a year and spend hours on each. It keeps me in control of every decision while surfacing trade-offs (cost vs. time vs. hassle) I'd otherwise miss.

**The 7 trip categories:** Where · When · Length of travel · Cost/Budget · Transportation · Accommodation · Top-level activities

## 3. What is in and out of scope?

- **One core workflow:** Enter knowns → pick the first decision → AI suggests options with trade-offs → compare the full picture for a 2–3 option shortlist → lock the decision → AI suggests the next decision (user chooses).
*You have six weeks. List the features, integrations, and polish you are deliberately NOT building.*

- [ ] Not building: Booking or payments (link out instead)
- [ ] Not building: Real-time price checking or price-drop alerts (AI estimates only until Build 3 tests real data)
- [ ] Not building: Group trip mode in the first version (same loop with multiple people's knowns — later build)
- [ ] Not building: Native mobile app (web only)

**Riskiest assumption:** AI-estimated costs, flights, and travel times are accurate enough to trust when comparing options. Without real data they may be wrong — the Build 3 "deal-checking agent" tests this.

### Why this needs AI (not just "faster")
Things a person can't realistically do by hand:

1. **"Watch out for" — what you didn't know to ask.** Flags hidden issues before you hit them: holidays that spike prices (e.g., Semana Santa in Antigua), tight connections at delay-prone airports, rainy season, long layovers that "save" money (my Lisbon mistake). **Included in the Build 1 prototype** on every option and comparison.
2. **Explore hundreds of combinations.** Checks destination × dates × routes × lodging at once and surfaces what-ifs ("shift 2 days and save $280", "fly into Liberia instead of San José"). Powers the full-picture comparison.
3. **Read everything for my concerns.** Reads thousands of reviews (in any language) to answer my questions — quiet? walkable? safe for solo travelers?
4. **Learn my taste.** Remembers I value total travel time over saving $200, what "moderate hiking" means for me, my vibe — so suggestions improve over time.
5. **Balance a whole group (later).** Weighs up to 15 people's budgets, dates, and dealbreakers fairly, and explains who gives up what.

**Positioning:** Travel AI is crowded (Mindtrip, Layla, Wanderlog, ChatGPT). Nextstop's edge is the approach — layered, I decide, trade-offs + full picture + "watch out for" — and the structure (remembers locked decisions, side-by-side comparisons, guides the next step) so I'm not managing a long back-and-forth chat.

**Agent vision (Build 3+):** An agent searches real sources — flights, hotels, Airbnb, Vrbo — to replace AI estimates with real prices and connections.

**What I learned testing it (Build 1):** I had an agent search Airbnb, Vrbo, and hotel sites for listings with specific qualities and report back. It worked, but these sites' terms of service prohibit bots and scrapers, and automated searching can get accounts flagged. Decisions:
- Nextstop will use **official data sources** (partner/affiliate programs and flight-data APIs) instead of scraping. Still need to research which accept student projects. Airbnb has no public API as far as I know.
- The app will **never log in to a user's account** on travel sites, and never book or message on their behalf.
- For my own research: agents browse logged out, in a separate browser profile, with small occasional searches.

## 4. Rough Local Prototype
*What did you spike this week to test the core idea, and what did you learn from throwing it at the problem?*

- **Local run command / branch / screenshot:** 
- **What worked vs. what surprised me:**
