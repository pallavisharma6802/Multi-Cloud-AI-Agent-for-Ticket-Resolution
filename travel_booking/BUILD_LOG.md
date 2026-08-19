# Travel booking system — build log

Running log, appended after every meaningful step. Started 2026-08-18,
continuing from Stage 1 (`DESIGN.md`, committed `b760a1f`).

## Confirmed decisions carried into Stage 2

- Capacity (`party_size` vs `max_occupancy`) is an explicit 4th hard check,
  alongside arrival-vs-check-in, budget, amenities.
- Cost math: `flight.price` is per-passenger, `hotel.price_per_night` (+
  `resort_fee_per_night`) is per-room. `total_cost = flight.price *
  party_size + (hotel.price_per_night + hotel.resort_fee_per_night) * nights`.
- Bedrock call budget: 80 total for this run. Tracked below after every
  batch of calls.

## Architecture decisions (before writing code)

**Intent-parsing agent: direct Bedrock structured call, not Azure NLP.**
Reused `app/llm/bedrock_client.py`'s `generate_structured` pattern as-is.
Reason: read `app/agents/azure_nlp_agent.py` — it's shaped entirely around
`analyze_ticket(title, description)` → NER/sentiment/key-phrases on support
tickets. Travel constraint extraction (party size, budget + its scope,
required amenities, destination, trip length) doesn't map onto that; generic
NER wouldn't reliably pull "family of 4" → `party_size=4` or "$200/night" →
`budget_scope=per_night_hotel`. The multi-cloud story is already established
by the ticket-resolution project; forcing Azure in here would add a layer
that does nothing but add latency and failure surface. Bedrock structured
output alone is the right tool for this extraction.

**Search agent: Pinecone + BM25 hybrid, reused from `retrieval_agent.py`'s
pattern, but as a new lightweight module, not the same class.** The
existing `PineconeClient.upsert_documents`/`query` hardcode a ticket-shaped
metadata payload (`text/source/category/intent/domain_pack`) that doesn't
fit hotel/flight records, so `travel_booking/agents/search_agent.py`
reimplements the same shape (dense Pinecone query + sparse BM25 + score
merge) directly against the Pinecone SDK, in new namespaces
(`travel-hotels`, `travel-flights`) inside the same existing `ticket-kb`
index (namespaces are how domain packs already separate data — same
pattern, not a new index). Embeddings via the same local
`sentence-transformers` `EmbeddingGenerator` — zero Bedrock cost.

**Critical: Search agent must NOT hard-filter on the fields Verification is
supposed to catch (amenity availability, resort fees, capacity, front-desk
hours).** If search pre-filters those out, the trap listings would never
reach Verification and the whole differentiator is untested. Search hard-filters
only on genuinely search-level facts: destination match and date
availability (`blackout_dates`, `available_from/to`) — a hotel that's sold
out for the requested dates wouldn't appear in a real search result either,
that's not a "trap," it's non-existence. Everything else (tags, price,
description) is used only for soft ranking. This is also where the
"genuinely can't be satisfied" test cases in Stage 3 come from — tight
availability + tight constraints can exhaust every candidate.

**Verification agent: deterministic Python, not an LLM call, for the actual
per-field comparisons.** This is the direct lesson from the MCP firewall
project's original bug (a single coarse LLM judgment instead of forced
per-parameter reasoning). All four hard checks here — time-of-day
comparison, budget arithmetic, amenity set-membership + note lookup,
capacity comparison — are 100% mechanically decidable from the structured
data; there is no ambiguity an LLM's judgment is needed to resolve, and
routing them through an LLM would add nothing but latency, cost, and a real
risk of arithmetic/date hallucination. So `verification_agent.py` computes
each check directly in Python and returns a structured
`VerificationResult` with one `CheckResult` per field (pass/fail + the
actual compared values), never a single holistic verdict. This also
protects the 80-call Bedrock budget — Stage 3's battery needs 15+ requests
x 2 runs = 30+ full pipeline runs; if verification burned a call too, that's
60+ calls just for checks that don't need judgment at all.
The one place natural-language generation legitimately belongs is turning
an already-computed structured result into UI copy (Stage 4) — that's
template-based off the real fields (same pattern as the firewall
frontend's `closing-message.ts`), not a second judgment call, so it costs
zero additional Bedrock calls either.

**Orchestration: LangGraph, reusing the project's proven graph pattern.**
`propose → verify → decide(accept/retry/escalate)` nodes, mirroring
`mcp_firewall/target_agent.py`'s shape. The decide node's logic is
deterministic (try next ranked candidate pair; if candidates exhausted,
escalate with the closest non-passing attempt reported) — nodes don't have
to be LLM calls, e.g. the firewall's own `execute` node isn't one either.

## Bedrock call tally

Running count of real Bedrock calls made this session (cap: 80).

- Intent Agent smoke test (2 calls): both correct on first try -- "family
  of 4... under $200 a night" correctly parsed `budget_scope:
  per_night_hotel`; "budget of $900 total" correctly parsed `total_trip`.
  Amenity synonym mapping and destination-code resolution both correct.
- Orchestrator end-to-end smoke tests (1 + 5 + 2 = 8 calls): see "Stage 2
  hand-picked smoke tests" below.
- Post-clarification-addition regression run (1 call): confirmed `run()`
  still works with the new date-default path.
- Clarification Flow A, 3 turns (3 calls) + Flow B, 2 turns (2 calls): see
  "Conversational clarification addition" below.
- **Running total: 16/80.**

## Stage 2 progress

- [x] Schemas (`travel_booking/agents/schemas.py`)
- [x] Config: added `model_travel_intent` (defaults to
  `amazon.nova-lite-v1:0`, same as every other role) + `travel_intent` role
  mapping in `model_router.py`.
- [x] Intent Agent (`travel_booking/agents/intent_agent.py`)
- [x] Search Agent (Pinecone hybrid, availability-only hard filter)
- [x] Verification Agent (4 deterministic per-field checks)
- [x] Orchestrator (LangGraph propose/verify/decide)
- [x] Conversational clarification addition (mid-stage requirement change)
- [x] Hand-picked smoke tests

## Stage 2 hand-picked smoke tests (orchestrator end-to-end)

Direct `VerificationAgent.verify()` unit tests (no Bedrock cost, run first
to validate the 4 checks in isolation before wiring the full pipeline):

| Combo | Expected | Result |
|---|---|---|
| H-AUS-02 (pool-closed trap) + F-AUS-01 | amenities FAIL, rest pass | ✅ correct -- caught "pool tagged but unavailable" |
| H-AUS-04 (capacity trap) + F-AUS-01, party=4 | capacity FAIL, rest pass | ✅ correct -- "sleeps 2" caught |
| H-AUS-05 (resort-fee trap) + F-AUS-01, budget $200/night | budget FAIL, rest pass | ✅ correct -- effective $224/night caught, listed $189 alone would have passed |
| H-AUS-03 (early desk close) + F-AUS-03 (23:55 arrival) | arrival_vs_checkin FAIL | ✅ correct -- "arrival AFTER desk closes" |
| H-AUS-06 + F-AUS-01, budget $2000 total, needs pool | all 4 pass | ✅ correct |

Full orchestrator runs (`TravelAgent.run(...)`, real Bedrock intent parse +
real Pinecone/BM25 search + deterministic verify/retry):

| Request | Result |
|---|---|
| "Family of 4 heading to Austin, need a pool, budget $2000 total, 3 nights" | verified, Congress Ave Grand Hotel + LA401, 1 attempt, all 4 checks pass |
| "Solo trip to Denver for 3 nights, need wifi and a gym, budget $250/night" | verified, Union Station Grand Hotel + VJ705 (00:05 arrival, 24hr desk correctly still passes), 2 attempts |
| "Family of 4 in Austin, need a pool, under $150 a night, 3 nights" | **unsatisfiable**, 12 attempts exhausted, closest attempt correctly reported as H-AUS-05 failing budget ($224/night effective vs $150 stated) -- honest rejection, no broken itinerary handed back |
| "Family of 3 wants a family-friendly lodge in Austin..." | verified, Congress Ave Grand Hotel, 1 attempt (search ranked a clean hotel above the H-AUS-04 capacity trap for this phrasing -- traps are provably caught when they DO get ranked into contention, per the direct verification tests above; Stage 3's battery deliberately forces trap contention by pairing traps with intent phrasing tuned to surface them) |
| "Solo business trip to Denver, need a gym..." | verified, Union Station Grand Hotel, 2 attempts |
| Two more targeted variants aimed at ranking H-AUS-04/H-DEN-03 first | both still resolved to the clean hotel on the first or an early attempt -- confirms the semantic ranker generally prefers well-rounded listings, which is why Stage 3 needs battery scenarios that don't rely on chance ranking to prove trap-catching, only on eliminating clean alternatives (e.g. destination-wide capacity/amenity requirements) |

**Conclusion**: all 4 hard checks fire correctly and independently (never
a single holistic verdict), both the accept path and the honest
"unsatisfiable, here's the closest miss" path work, and traps are
provably caught whenever a search ranks them into contention. Stage 2's
done-criteria are met.

## Conversational clarification addition (mid-Stage-2 scope change)

Landed while Stage 2 was still open (orchestrator done, smoke tests not
yet finished) -- folded into Stage 2 per the instruction to do so if not
yet past it. This also surfaced and fixed a real pre-existing gap: the
original orchestrator never actually filtered flights by date at all --
any of the 6 flights per destination could be picked regardless of what
the user meant by "October." Fixed by adding `date_range_start/end` to
the schema and a hard filter in `orchestrator.py`'s
`_build_candidate_queue` (flights outside the resolved range are excluded
before ranking, not just soft-penalized).

**Design**: completeness (dates specific enough / party size clear /
budget has a real number) is evaluated with deterministic code
(`_evaluate_completeness` in `intent_agent.py`), not the LLM's own
self-report of whether it's done -- same principle as Verification:
don't trust a holistic self-judgment for something mechanically checkable.
The LLM only flags the two things code genuinely can't detect from
structure alone -- `party_size_ambiguous` (text implies a group with no
count) and `budget_mentioned_vague` (cost referenced with no number) --
everything else (date range width, whether a number is present) is
checked directly on the extracted fields.

Each turn re-parses the ENTIRE transcript (not a diff/merge of just the
new message) with an explicit instruction that later statements override
earlier ones. This was a deliberate simplicity choice over manual
per-field state merging: it makes corrections "free" (the LLM just re-reads
a transcript where the correction is the most recent relevant statement)
at the cost of one full re-parse per turn, which is affordable given the
5-exchange cap.

Clarifying questions are deterministic templates (`_next_question`), not
a second LLM call -- there are only 3 possible gap types, so templating
costs zero extra Bedrock calls and is fully predictable to test.

**Test 1 (answers clarifying questions in sequence)**: "We want to go to
Miami sometime in October, not too expensive, need a pool."
- Turn 1: `needs_clarification`, missing=[dates, budget], asked about dates first (priority order: dates > budget > party_size).
- Turn 2 answer "Let's say October 5th to 9th.": missing=[budget] only, dates resolved to 2026-10-05..2026-10-09, asked about budget.
- Turn 3 answer "Around $180 a night.": `ready`, all fields resolved correctly (`budget_amount=180, budget_scope=per_night_hotel`), confirmation message correctly stated: "Got it -- searching for a 1-person trip, 2026-10-05 to 2026-10-09, under $180/night, need pool." ✅

**Test 2 (correction mid-conversation, the user's own example)**: "Trip to
Denver, Oct 6-8, budget $200 a night, need wifi." -> immediately `ready`
(no clarification needed, request was already complete on turn 1),
confirmation correctly said "...a 1-person trip...under $200/night...".
User then sends "Actually make that $250 and 2 people." (an unprompted
correction, not an answer to a pending question) -> re-parsed over the
full transcript -> `budget_amount` updated 200->250, `party_size` updated
1->2, confirmation message correctly updated to "Got it -- searching for
a 2-person trip, 2026-10-06 to 2026-10-08, under $250/night, need wifi."
Old values did not leak forward. ✅

Both flows confirmed: dates/budget/party-size gap detection, one-question-
at-a-time behavior, mid-conversation correction without state loss, and
the final confirmation message accurately reflecting the whole
conversation, not just the first message.

**Stage 4 UI note (carried forward)**: the intake phase must be a real
multi-turn chat using `IntentAgent.start()`/`continue_conversation()` +
`TravelAgent.run_from_state()`, not a single input box. Search-results/
verification view still comes after intake reaches `ready` or
`best_effort`.

**Stage 3 re-verification note**: Stage 3 hasn't started yet, so no
re-verification needed there -- this is folded into Stage 2 cleanly
before Stage 3 begins. The battery (Stage 3) will use `TravelAgent.run()`
(the one-shot, best-effort-resolves-immediately entry point) with fully-
specified requests, not the interactive clarification loop -- that loop
is exercised directly above and will be exercised again end-to-end in
Stage 4's UI testing.

## Stage 3: test battery

`travel_booking/eval/battery.py` -- 15 hand-designed scenarios x 2 runs =
30 real end-to-end runs (real Bedrock intent parse, real Pinecone/BM25
search, deterministic verify/retry). Results: `travel_booking/eval/battery_results.jsonl`
(30 lines, one per run, full attempt log + check-level detail per run),
summary: `travel_booking/eval/summary.json`.

Before writing the battery, added `attempt_log`/`all_attempts` to the
orchestrator/schemas (`orchestrator.py`, `schemas.py`) so every attempted
combination is recorded, not just the final accepted/closest-failed one --
needed to precisely assert "was this specific trap combo tried and
correctly rejected" rather than inferring it from the final booking
outcome, since a request can succeed on a later, different combination
after an earlier one is correctly rejected.

**Scenario design**: every trap scenario is constructed so the trap hotel
is the ONLY candidate matching the stated amenities within the stated
budget/date window (worked out by hand against the real `hotels.json`
data before running anything) -- Stage 2's own smoke tests showed the
semantic ranker often prefers well-rounded clean listings over a trap
even when the trap is a plausible surface match, so relying on ranking
luck to force contention would have under-tested the battery. Combination
scenarios (2) instead assert on the attempt log directly: at least one
attempt in the whole run failed ONLY `arrival_vs_checkin` while the other
3 checks passed on that same attempt -- proof of a genuine
combination-only rejection, independent of whatever the final booking
outcome ends up being.

### Results

| Category | Runs | Matched expectation |
|---|---|---|
| clean (3 scenarios x2) | 6 | 6/6 |
| trap (7 scenarios x2) | 14 | 14/14 |
| combination-only (2 scenarios x2) | 4 | 4/4 |
| unsatisfiable (3 scenarios x2) | 6 | 6/6 |
| **Total** | **30** | **30/30 (100%)** |

**Trap catch rate: 14/14 = 100%.** Every one of the 7 designed traps
(pool-tagged-but-closed x2, gym-inaccessible, pet-restricted-seasonally,
resort-fee-hidden-cost x2, capacity) was correctly rejected on exactly
the expected check, both runs, with every other check on that same
attempt correctly passing (no check fired that shouldn't have).

**False positives: 0.** No clean scenario failed to verify; no trap
scenario had an unexpected second check fail alongside the intended one.

**False negatives: 0.** No trap's specific check passed when it should
have failed -- no trap slipped through.

**Combination-only failures: confirmed real, both scenarios, both runs.**
`H-AUS-03 + F-AUS-03` and `H-DEN-02 + F-DEN-06` each showed an attempt
that failed ONLY `arrival_vs_checkin` with budget/amenities/capacity all
passing on that same attempt -- exactly the "neither record is wrong
alone" case the dataset was built to exercise. Both of these specific
requests ended in `unsatisfiable` overall (their date range was too wide
for a same-hotel early-flight alternative to also clear every other
check within the attempt cap), which is itself an honest, correct result,
not a test artifact.

**Unsatisfiable-with-no-valid-combination: confirmed, all 3 mechanisms
distinct and correctly identified**:
- `unsat_blackout_collision`: the availability *gate* (not verification)
  correctly skipped H-AUS-05 for Oct 19-21 without ever calling Verify on
  it, while the other 5 Austin hotels were verified and correctly
  rejected on amenities (missing pet_friendly) -- closest attempt
  reported was H-AUS-06, the best partial match.
- `unsat_no_destination`: correctly short-circuited before any search at
  all (`attempts_tried=0`), since Seattle isn't a served destination.
- `unsat_impossible_amenity_combo`: correctly explored all 6 Denver
  hotels (12 attempts across both flights) and correctly reported none
  could ever satisfy pool+pet_friendly together, regardless of budget.

**One honest observation, not a correctness bug**: 12 of the 30 runs hit
a transient empty-response retry from Bedrock (`Bedrock output failed
schema validation... Expecting value: line 1 column 1`), auto-recovered
by `bedrock_client.py`'s existing retry logic (all 30 runs still
succeeded on retry). This roughly doubles some requests' real Bedrock
call count. Didn't chase the root cause further -- self-resolved every
single time, well below the "stop and log" threshold for a recurring
blocking error (bound #2), and the longer transcript-based prompt used
for the multi-turn-capable `_parse_transcript` (vs. the shorter one-shot
prompt from the Stage 2 smoke tests, which never hit this) is the most
likely factor, worth a look if it gets worse under heavier use.

**Bedrock calls**: 30 base + 12 retries = 42 for the battery.
**Running total: 16 (Stage 2) + 42 (Stage 3) = 58/80.**

No test case expectations needed correcting -- all 15 scenarios were
verified by hand against the real dataset before running, and all 30
runs matched on the first execution of the battery.
