# Travel Desk

A trip planner that checks a hotel and a flight against each other before
calling anything "verified" — arrival time vs. check-in, combined budget,
amenities, and room capacity. Real flight and hotel data via SerpApi
(Google Flights / Google Hotels), not a mock dataset.

## Why the checks matter

A hotel that's in budget and a flight that's in budget don't guarantee a
trip that works. A flight landing at 11pm against a hotel whose desk closes
at 10 is a real, common failure that neither price nor a star rating would
catch. This app runs a small set of hard checks on the *pair*, not each
piece in isolation, and shows exactly which check failed when something
doesn't work — never a silent "closest match."

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env   # SERPAPI_API_KEY, AWS creds for Bedrock, TRAVEL_DATABASE_URL
uvicorn travel_booking.api:app --reload --port 8200
```

Needs a Postgres database (`TRAVEL_DATABASE_URL`) and a SerpApi key. AWS
Bedrock parses freeform requests ("family of 4 to Miami, need a pool, $2k
total") into structured search parameters.

## Layout

```
api.py                       FastAPI app, all routes
auth.py                      password hashing, sessions
db.py                        Postgres connection + schema
agents/
  intent_agent.py            freeform text -> structured trip request
  orchestrator.py            search + verify loop (LangGraph)
  verification_agent.py      the 4 hard checks
  ranking.py                 scores verified pairs (price/quality/convenience/amenities)
  serpapi_client.py          live Google Flights / Hotels
  browse.py                  standalone hotel/flight browsing (no pairing)
  preference_aggregator.py   combines group members' preferences (bandit)
  explanation.py             turns a verification result into UI copy
frontend/                    single-page UI, no build step
eval/battery.py              deterministic verification + ranking evals
```

## What "verified" checks

1. **Arrival vs. check-in** — does the flight land in time to actually check in
2. **Budget** — flight + hotel + mandatory fees, computed together
3. **Amenities** — checked against real availability, not just a listing tag
4. **Capacity** — party size against the room's actual max occupancy

## Ranking

Verification is a hard gate (pass/fail), not a ranking signal. Among pairs
that pass, `agents/ranking.py` scores each on price, hotel rating, flight
convenience (nonstop + buffer before the desk closes), and how many
amenities it offers beyond what was required. Four presets --
`best_value` (default), `cheapest`, `highest_rated`, `most_convenient` --
weight those differently; the UI exposes this as a sort control.

## Eval

```bash
python travel_booking/eval/battery.py
```

Two deterministic evals against hand-crafted fixtures, no live API calls:

- **Verification correctness**: precision/recall over individual checks
  across a dozen planted scenarios (clean passes, amenity/budget/capacity/
  arrival traps, real-data gaps that must read as "unverifiable" not
  "passed").
- **Ranking quality**: each scenario hand-designs which candidate *should*
  win under a given preset, then checks whether it does. (Sorting a pool by
  its own score is a tautology; this instead checks the scoring against an
  independent, intended answer.)

Results land in `eval/battery_results.jsonl` (per-scenario) and
`eval/summary.json` (aggregate numbers).

## Tests

```bash
pytest tests/test_travel_booking.py
```

Needs a reachable Postgres (the tests truncate tables between runs, they
don't create a throwaway database). For local testing:

```bash
docker run -d -e POSTGRES_PASSWORD=test -e POSTGRES_DB=travel -p 5433:5432 postgres:16-alpine
TRAVEL_DATABASE_URL=postgresql://postgres:test@localhost:5433/travel pytest tests/test_travel_booking.py
```
