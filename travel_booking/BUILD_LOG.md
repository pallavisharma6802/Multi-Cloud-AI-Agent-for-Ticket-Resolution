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

## Stage 4: local UI

Single-view FastAPI + vanilla HTML/CSS/JS (`travel_booking/api.py`,
`travel_booking/frontend/index.html`) -- no Next.js/framer-motion this
time, deliberately: the brief explicitly said "not split-screen... more
like a normal booking result page," and this UI has no interception
moment to pace or dramatize the way the MCP firewall demo did, so a
heavier frontend stack would add nothing. One process, one port (8200),
serves the JSON API and the static page.

**Flow**: a real multi-turn chat (`POST /api/chat/start`,
`POST /api/chat/reply`, in-memory `ConversationState` per
`conversation_id`) drives intake through `IntentAgent.start()`/
`continue_conversation()` exactly as built and tested in Stage 2 -- not a
single input box. Once status reaches `ready`/`best_effort`, the frontend
automatically calls `POST /api/search/{conversation_id}`, which runs
`TravelAgent.run_from_state()` and returns the real `ItineraryOutcome`
plus a `build_explanation()` payload (`travel_booking/agents/
explanation.py`) -- template-only, assembled directly from each
`CheckResult`'s already-human-readable `detail` string (written by
Verification for exactly this purpose), never hardcoded copy and never a
second LLM call.

**Images**: served locally from `travel_booking/data/images/` via a
mounted static route (`/images/hotels/{id}.jpg`, `/images/flights/{id}.jpg`)
-- same Stage 1 Picsum files, cosmetic only.

**End-to-end verification** (3+ required battery scenarios, tested against
the real running server, not mocked):

1. `clean_austin_family` (verified path) -- via curl against the real
   API: chat reached `ready` in one turn, search returned
   `status=verified`, Congress Ave Grand Hotel + LA401, all 4 checks
   shown passing with real detail text, total cost $1575.00 matched the
   hand-computed figure. Both hotel and flight images confirmed
   reachable (`HTTP 200`) at their `/images/...` URLs.
2. `trap_aus02_pool_closed` (trap/unsatisfiable path) -- correctly
   returned `status=unsatisfiable` with a real per-field checklist
   (3 pass, 1 fail). Worth noting honestly: the "closest attempt" surfaced
   was `H-AUS-05` (the resort-fee trap) rather than `H-AUS-02` (the
   pool-closed trap) -- both are legitimately "one check away" for this
   request (H-AUS-05's listed $189 is itself already over the stated
   $150 budget, independent of its fee), and the orchestrator's
   closest-attempt tracker keeps whichever tie it finds first rather than
   preferring one arbitrarily. Not a bug -- both are real traps and the
   UI correctly showed one of them being caught with an honest headline
   and full explanation.
3. `unsat_no_destination` ("Seattle") -- interesting real interaction:
   this exact wording has no explicit date range ("3 nights" is a
   duration, not dates), so the real interactive chat correctly asked a
   clarifying question about dates FIRST, before ever reaching the
   destination check (the battery's one-shot `run()` bypasses
   clarification entirely, so this distinction only shows up when
   driven through the real conversational API, which is exactly what
   Stage 4 is supposed to test). Answered "Oct 10-13", conversation
   reached `ready`, search then correctly returned
   `status=unsatisfiable`, `attempts_tried=0`, headline: "Couldn't search
   at all -- \"Seattle\" isn't a destination this system currently serves
   (only Austin, Denver, and Miami)."
4. `clean_denver_solo`, driven through an actual browser tab (not curl)
   via the Claude Browser tools -- typed the request, clicked Send,
   watched the chat confirm understanding, watched it auto-trigger
   search, and got back a fully rendered result card: hotel photo,
   flight photo, green "Verified" headline, and all 4 checks listed with
   real text ("Union Station Grand Hotel has a 24-hour front desk, so
   the 10:45 arrival on LA512 can check in at any time", etc.).
   Screenshot-verified. Console checked, zero errors.

**One real bug found and fixed via this browser test**: the status line
stayed on "searching..." after results rendered (never updated on
completion) -- fixed by setting it to "status: done (...)" right after
the search response lands, in `frontend/index.html`. Re-verified the fix
loads (fresh page load confirmed the corrected JS is served -- didn't
re-spend a Bedrock call re-running the full flow for a one-line
cosmetic-only text update with no logic change).

**Environment note, not an app defect**: `preview_start`/`navigate`
against `localhost:8200` initially failed with a spurious "port 3000 in
use by com.docker.backend" error, unrelated to this app's actual port
config (tried `port`, `autoPort:false`, and `autoPort:true` in
`.claude/launch.json`, all hit the same error). Worked around by opening
a fresh tab (`tabs_create`) and navigating directly, which succeeded and
was used for verification #4 above. Not investigated further since a
working path was found quickly.

**Bedrock calls this stage**: 5 (2 curl end-to-end tests with 1-turn
intake + 1 curl test with 2-turn intake + 1 browser-driven test).
**Running total: 58 (Stage 2+3) + 5 (Stage 4) = 63/80.**

## Final status

All 4 stages complete and meet their checkable "done" criteria:

- **Stage 1**: 18 hotels + 18 flights, 7 hand-built traps, images sourced
  and downloaded locally, full design writeup in `DESIGN.md`.
- **Stage 2**: all 4 hard checks implemented as explicit, independent,
  deterministic per-field comparisons (never a holistic LLM judgment);
  conversational clarification agent added mid-stage per updated
  requirements, both required flow types (answer a question, correct an
  earlier answer) verified working.
- **Stage 3**: 30/30 real end-to-end runs matched hand-verified
  expectations. **Trap catch rate: 100% (14/14). False positive rate: 0%.
  False negative rate: 0%.** No test expectations needed correcting.
- **Stage 4**: local single-view UI, real multi-turn chat intake, results
  generated from real verification output, verified against 4 real
  end-to-end scenarios (3 via API, 1 via an actual browser tab with a
  screenshot and a real bug found and fixed), zero console errors.

**Total Bedrock calls used: 63/80** (within the 80-call cap; roughly 17
calls of headroom remained unused).

**Not fully done / deferred, and why**: no cloud deployment (correctly
out of scope per the explicit hard bound -- local-only for this
project). The stale `frontend/.next` artifact directory that
reappeared twice during this session at the OLD pre-Stage-1 `frontend/`
path (unrelated to any command this session ran, `ps aux` found no
live process writing it) was deleted both times it appeared; if it
recurs again in a future session it's worth a real investigation, not
just repeated cleanup.

No history rewriting was performed at any point. Every stage was
committed as its own normal commit with an honest message once its
done-criteria were met (`b760a1f` Stage 1, `8b818a2` Stage 2, `02d537f`
Stage 3, `ce5caa1` Stage 4 functional).

## Stage 4 visual redesign (post-functional pass)

Requested after Stage 4's functionality was already confirmed and
committed -- explicitly scoped as visual-only, no logic changes except
one: `explanation.py`'s `_checklist()` was missing `actual`/`expected`
from each `CheckResult` (only `label`/`passed`/`detail` were exposed),
which the new design needs to show a real numeric/text comparison per
check instead of only a prose sentence. Added those two fields through
to the frontend; this is additive (new fields), nothing existing changed
shape.

**Design process**: read the same `frontend-design` skill used for the
MCP firewall redesign
(`~/.claude/plugins/marketplaces/claude-plugins-official/plugins/frontend-design/skills/frontend-design/SKILL.md`,
not separately invocable as a slash-skill in this session, read directly
as source). Brainstormed a token system before writing any code and
checked it against the skill's three named AI-design-default clusters
(cream+serif+terracotta; near-black+one neon accent; broadsheet
newspaper) to make sure this wasn't defaulting to one of them.

**Concept**: "ticket/departure-board," grounded in the subject itself
(travel documents, boarding passes, airport signage) rather than reusing
the MCP firewall project's dark-terminal identity, which is a different
project with a different personality (adversarial/security vs.
transactional/booking). Most of the page is a warm ivory "ticket stock"
zone with a faint ruled-paper background and a dashed perforation
divider (a structural device that's actually true of the subject --
ticket stock is perforated -- not decoration for its own sake). The
verification section breaks from that into a dark charcoal "departure
board" zone -- a deliberate, justified risk per the skill's "take one
real risk" guidance, reserved for the one section the user explicitly
named as the signature moment.

**Type**: Archivo (700/800) for display/headings, Inter for body copy,
Space Mono for all data -- flight numbers, times, prices, the board's
comparison values -- since ticket data is classically monospace-stamped.
Three distinct accent hues, each scoped to one semantic role only
(never reused across roles, same discipline as the firewall project's
verdict colors): steel blue for transit, terracotta for lodging, amber
for the board/confirmation moments.

**Requirement-by-requirement**:
1. Skill followed as above, concept and tokens chosen before code.
2. Chat now has 3 visually distinct message treatments: a question
   (paper bubble, amber-tagged, asymmetric corner) vs. a confirmation
   (bordered "stub" with a stamp icon and monospace receipt-style text,
   not a bubble at all) vs. searching (a dark pill with 3 amber pulsing
   flap-dots, replacing the old static gray "status: searching..." text
   entirely) -- confirmed live: the searching pill was caught mid-render
   in an actual test run (screenshot in this session's browser history).
3. Hotel and flight cards now carry distinct icon/accent tags (🏨
   terracotta "Lodging" vs. ✈ blue "Transit") but share one joined frame
   with a circular link-icon badge straddling the seam between them --
   reads as one evaluated pair, not two unrelated cards.
4. The verification board is the dominant element on the page once it
   lands: dark zone, large glowing banner (amber for verified, red for
   unsatisfiable -- deliberately equal visual weight, differentiated only
   by hue/glow-color, not by one being louder than the other), each
   check row shows the actual compared value against the limit as two
   distinct styled tokens (e.g. `$224.00/night` in a red pill vs.
   `<= $150.00/night`) alongside the prose detail, and rows reveal with a
   staggered 3D flip-in animation (160ms apart) rather than appearing at
   once. `prefers-reduced-motion` is respected (animations disabled,
   final state shown immediately).

**Verification**: ran 2 real end-to-end requests through the actual
redesigned UI in a real browser tab (not curl this time, since this was
a visual pass) -- one clean pass (`clean_austin_family`-equivalent,
green "Verified" banner, all 4 checks passing with real values) and one
trap (`trap_aus02_pool_closed`-equivalent, red "Couldn't fully satisfy"
banner, the resort-fee trap's real $224.00-vs-$150.00 comparison visibly
failing while the other 3 checks correctly show passing). Screenshot-
verified both states at desktop width (800x1700, to see the full board
without needing to scroll) and confirmed the layout holds up at mobile
width (375x812) with no horizontal overflow.

**Tooling hiccup, not an app bug**: the Browser pane's `scroll` action
hung/timed out repeatedly in this session, and one screenshot briefly
returned a stale cached frame after a scroll timeout (confirmed via
`get_page_text` and a direct `getComputedStyle` check that the real DOM
state was already correct -- `opacity: 1`, correct color, correct
layout -- while the screenshot lagged behind). Worked around by resizing
the viewport tall enough to avoid scrolling entirely, and by closing and
reopening a fresh tab, both of which resolved it cleanly. Not a defect
in `index.html`.

**Bedrock calls this pass**: 2 (one verified-path test, one trap-path
test, both driven through the real browser). **Running total: 63 + 2 =
65/80.**

Committed as its own follow-up commit after this log entry, since the
user's redesign request landed after Stage 4's functional commit was
already made.

## Bug found via live user testing: clarification loop re-asked its own question

User tried the redesigned UI, asked for Miami "sometime in October", got
asked "...or should I search across the whole month?", answered "whole
month" -- and got asked the exact same question again instead of
proceeding. Real bug, not a misunderstanding: the question itself
offers "whole month" as a valid path, but nothing in the schema let the
LLM represent "user explicitly declined to narrow" as a resolved state
distinct from "still vague" -- so `_evaluate_completeness` kept
flagging dates as missing no matter what the user said in response to
that specific question.

**Fix**: added `dates_whole_month_ok: bool` to `TravelConstraints`
(`schemas.py`), with explicit prompt guidance in `intent_agent.py`'s
`SYSTEM_CONTEXT` telling the model to set it when the user was asked
this exact question and chose the whole-month path. Completeness
checking and constraint resolution both updated to treat that as
resolved (defaults to the full `2026-10-01..2026-10-31` range, same as
before, but the assumption message now correctly says "searching the
whole available month, as you asked" instead of the misleading
"no specific dates given").

**Verified**: reconstructed the exact failing transcript (asked about
dates, replied "whole month") and confirmed `dates_whole_month_ok=true`
is now set and `dates` no longer appears in `missing`. 1 Bedrock call
used for this reproduction test (2 more were spent on an earlier
un-forced `start()`+`continue_conversation()` run before I isolated the
repro this way, whose turn-1 extraction happened to resolve dates
differently than the user's original run due to normal temperature-0.1
variance -- not itself a bug, just not a controlled reproduction, so I
discarded that path once I had a clean isolated repro). Did not re-run
the full 30-run Stage 3 battery for this -- the change only activates
when `dates_whole_month_ok` is set, which requires a two-turn
conversational context none of the battery's one-shot requests produce,
so the existing battery results aren't affected by this change; noting
that reasoning here rather than spending ~30 more Bedrock calls to
reconfirm something structurally unreachable by those requests.

**Bedrock calls this fix**: 3. **Running total: 65 + 3 = 68/80.**

**Still open, pending user input** (raised in the same message as the
bug report, not yet actioned): (1) general "it looks bad" feedback on
the redesign with no specifics yet -- asked the user what specifically
isn't working since guessing and re-redesigning blind would waste their
time; (2) a request to replace the simulated dataset with a real
"Google hotels and flights implementation" -- flagged rather than
started, since this directly reverses the project's original explicit
constraint ("fully simulated data, no real travel APIs, no new billing
relationships") that Stage 1 was built around, and no such public
Google API actually exists for this (Google Flights has no public API;
the closest real options are paid third-party services like SerpApi's
Google Hotels/Flights scraping endpoints or Amadeus for Developers,
both of which are new paid billing relationships) -- needs the user's
explicit direction before any code changes, not an assumption.

## User feedback resolved: visual direction + real-API decision

Asked two follow-up questions to get specifics (the first round of
feedback was "it looks bad" with no detail, and "Google hotels and
flights" isn't an API that actually exists). Answers:
- Visual: "Clean modern travel-app style" -- bright, simple,
  Airbnb/Kayak-like cards, no thematic concept. Explicit rejection of
  the ticket/departure-board direction from the prior pass.
- Data: "use a real booking api on free tier" -- confirmed they do want
  live real-world data, any provider, free tier.

**Visual redesign v2**: full rewrite of `frontend/index.html`, dropped
the departure-board dark section, the 3-typeface system, and all the
per-role accent hues entirely. Now: single Inter typeface, white cards
on a light gray background, one confident blue brand accent
(`#1967d2`), standard green/red pass-fail treatment, plain checkmark/x
icons instead of flip-board animation, simple fade-free rendering. This
is a deliberate move AWAY from the frontend-design skill's "take one
real risk" posture, because the user explicitly asked for the opposite
-- a familiar, unremarkable consumer-app look, which is itself a valid
design brief the skill doesn't override.

**Real bug fixed in the same pass**: caught via the user's own testing
-- the dates-clarification question explicitly offers "search the whole
month" as an answer, but replying with almost exactly that phrase got
the identical question re-asked instead of proceeding (see the
dedicated bug-fix entry above, committed separately as `0822814` before
this visual pass). Re-verified live through the actual redesigned UI
(not just the isolated repro test) -- reproduced the user's exact
conversation (Miami, "not too expensive", "whole month") end to end:
correctly resolved to the full `2026-10-01..2026-10-31` range, correct
assumption text ("searching the whole available month, as you asked"),
no repeated question, and the search that followed correctly proposed
an itinerary and correctly flagged it as `unsatisfiable` (a pool-less
budget hotel was the closest match; amenities check correctly failed
while the other 3 checks correctly passed).

**Secondary fix found via this same test**: Enter-to-send wasn't firing
reliably when driven through the Browser pane's synthetic key events
(`e.key` check alone). Added a `e.keyCode === 13` fallback alongside it
in `index.html` -- low-risk, additive, real keyboards fire both
properties correctly so this doesn't change behavior for actual users,
just hardens against however that event was being dispatched.

**Bedrock calls this round**: 3 (the live 3-turn UI reproduction).
**Running total: 68 + 3 = 71/80.**

**Real booking API -- next step, not yet started**: needs a decision on
provider before any code changes. Recommending **Amadeus for
Developers** (their free "Self-Service" tier covers Flight Offers
Search and Hotel Search, no credit card required to sign up) over
SerpApi's Google-scraping endpoints, since Amadeus is a real airline/GDS
data provider rather than a scraper, and its free tier is actually
usable for a demo rather than a 100-search/month trial. This requires
the user to create their own free Amadeus for Developers account and
provide an API key + secret (cannot be done on their behalf -- account
creation and credential handling are both outside what this session can
do directly). Proposed next steps once credentials are available: (1)
build an `amadeus_client.py` module (OAuth2 client-credentials token
flow + Flight Offers Search + Hotel Search calls) behind a config flag,
(2) keep the existing simulated Search Agent as a fallback/demo mode
rather than deleting it outright, since Stage 1-3's entire verification
methodology (the 7 hand-built traps, the 100% catch-rate battery) was
built and proven against it, (3) re-evaluate what "trap" testing even
means against live real-world data, which won't have engineered flaws
the way the simulated dataset does, but will have real naturally-
occurring edge cases (real check-in policies, real fees, real capacity
limits) that the same 4-check Verification Agent logic should still
catch correctly without modification, since it operates on whatever
structured fields the data source provides, real or simulated.

## Real-API decision revised: Amadeus dead, going with SerpApi Google Flights/Hotels

The user visited developers.amadeus.com directly and found the free
self-service portal was decommissioned July 2026 -- what's left is an
"Enterprise API Portal" requiring a sales/access-request process, not a
quick free signup. My earlier recommendation was stale. Re-researched
live via WebSearch rather than relying on memory a second time:

- Kiwi.com Tequila: no longer self-serve, invite-only now.
- Skyscanner API: partner-only, no public free tier.
- Duffel: genuinely free self-serve signup, but test mode returns
  Duffel's own mock airline data, not live real-world fares; real fares
  require a paid pay-as-you-go tier.
- StayAPI: real free tier (50 requests, no card) for hotels only,
  aggregates several real platforms.

None of these matched the user's literal original ask ("Google hotels
and flights") until checking **SerpApi's Google Flights API and Google
Hotels API** specifically -- not an official Google product (none
exists), but SerpApi legitimately queries Google's own real travel
search results and returns them as structured JSON, so the underlying
data genuinely is what Google Flights/Hotels shows. Free tier is
~100-250 searches/month, self-serve. User confirmed: go with this.

**Verified real request/response shapes via WebFetch against SerpApi's
own docs pages before writing any code** (given the Amadeus miss, did
not rely on memory this time):
- `GET https://serpapi.com/search?engine=google_flights&departure_id=...&arrival_id=...&outbound_date=...`
  -> `best_flights`/`other_flights` arrays, each with `flights[]` legs
  (`departure_airport.time`, `arrival_airport.time`, `airline`,
  `flight_number`), `price`, `booking_token`.
- `GET https://serpapi.com/search?engine=google_hotels&q=...&check_in_date=...&check_out_date=...`
  -> `properties[]`, each with `rate_per_night.extracted_lowest`,
  `total_rate.extracted_lowest`, `amenities[]` (free text),
  `check_in_time`/`check_out_time` (12h string), `images[].thumbnail`,
  `overall_rating`, `property_token`.

**Built `travel_booking/agents/serpapi_client.py`**: `search_flights()`
and `search_hotels()`, normalizing real responses toward the same shape
`data/flights.json`/`data/hotels.json` already use, so the rest of the
pipeline (constraints, verification) doesn't need to know which source
it's looking at. Added `serpapi_api_key`/`travel_data_source` to
`app/config.py` (defaults: unset / `"simulated"` -- nothing changes for
existing runs) and documented both in `.env.example`.

**Honest, important gap found while building this, not glossed over**:
the real Google Hotels search response does NOT include front-desk
hours or room/max-occupancy data at all -- both are fields the
simulated dataset invented specifically to exercise the
arrival-vs-check-in and capacity checks. Against real data:
- `arrival_vs_checkin` could only compare against `check_in_time`, not
  "does the desk close before a late arrival" -- that whole trap
  mechanism (H-AUS-03, H-DEN-02 in the simulated set) has no real-data
  equivalent from this endpoint.
- `capacity` cannot run at all against this data as retrieved here (no
  occupancy field in the search response).
- `amenities` still works, but amenity strings are free text ("Air
  conditioning", "Free Wifi") rather than the simulated dataset's exact
  controlled vocabulary, so matching has to be fuzzy/substring-based,
  not exact membership.
- `budget` translates cleanly, and better than expected: comparing
  `rate_per_night` against `total_rate / nights` reveals real mandatory
  fees not in the headline rate -- a naturally-occurring real-world
  equivalent of the simulated resort-fee trap, discovered rather than
  invented.

Marked each of these clearly in the module docstring and inline in the
normalized hotel dict (`front_desk_24hr`/`front_desk_closes`/
`max_occupancy` all explicitly `None` when sourced from SerpApi,
`resort_fee_inferred: true` flag on the computed fee) rather than
silently defaulting them to something that would make the checks look
like they still work the same way against real data. **Not yet
resolved**: whether to drop the capacity check entirely in `serpapi`
mode, degrade `arrival_vs_checkin` to a weaker check-in-time-only
comparison, or find a different real data source/endpoint that does
expose these -- needs a decision, flagged for next session/turn rather
than silently picked.

**Not yet wired into `TravelAgent`/the orchestrator, and not yet tested
against live data** -- no API key exists yet (user needs to sign up
free at serpapi.com and provide it). The module raises a clear
`SerpApiError` if called without a key, verified working. Import and
error-path both confirmed working, `pytest` unaffected (14/14 still
pass) -- this is purely additive, no existing code path changed. Zero
Bedrock calls this step (pure research + scaffolding). **Running total
unchanged: 71/80.**

## Real SerpApi data wired in and verified live

User added `SERPAPI_API_KEY` to `.env` and asked to wire it up. Verified
the key works with two direct live calls before touching the pipeline
(`search_flights('ORD','AUS','2026-10-05')` returned 11 real United
flights with real prices; `search_hotels('hotels in Austin, TX', ...)`
returned 20 real listings with real amenities/ratings/images) --
confirmed the client module built in the last commit actually works
against a real key, not just that it imports cleanly.

**Two real bugs found and fixed while wiring, before any live pipeline
test**:
1. `verification_agent.py` used `hotel.get("resort_fee_per_night", 0)`
   in two places -- `dict.get(key, default)` only falls back when the
   KEY is missing, not when it's present and `None`. SerpApi-sourced
   hotels always set that key (to `None` when uncomputable), so this
   would have crashed with `price + None` the first time budget was
   checked against real data. Fixed to `(hotel.get(...) or 0)`.
2. `serpapi_client.py` could pass a listing through with a `None`
   price/arrival-time if SerpApi didn't return one for some property --
   would have broken the budget/arrival checks downstream. Fixed by
   skipping any flight/hotel result missing a usable price or parseable
   times at the source, rather than letting a null leak into
   Verification.

**Made the "data gap" honest instead of silently working around it**
(the gap flagged in the prior commit -- no front-desk-hours or
room-capacity fields in real Google Hotels data): added
`CheckResult.data_available: bool` (default `True`, so every existing
Stage 2/3 result and the battery's 100% catch rate are completely
unaffected). When a check genuinely can't be evaluated from the data
source, it now returns `passed=True` (a placeholder that never wrongly
blocks a booking) with `data_available=False`, and both
`explanation.py` and the frontend render that as a distinct
"not verifiable" state -- gray "?" icon, no fake comparison numbers,
never shown as a real green pass. The top-level "Verified" headline
also changes wording when this happens ("Verified everything this data
source could check -- X, Y couldn't be confirmed...") instead of
claiming full verification it didn't actually do.

**Amenity matching made fuzzy for real data**: real Google Hotels
amenities are free text ("Outdoor pool", "Free Wi-Fi", "Fitness
center"), not the simulated dataset's exact controlled vocabulary.
Added a small synonym table + substring matching
(`_amenity_present()`), falling back to exact match first so the
simulated dataset's behavior is completely unchanged.

**Orchestrator now branches on `settings.travel_data_source`**:
- `_build_candidate_queue_serpapi()` -- deliberately does NOT search
  every day across a wide/whole-month range the way simulated mode
  does, since real flight search is one API call per date and the free
  tier has a real monthly cap. Uses exactly `date_range_start` for the
  flight search and one hotel search across the full stay -- 2 API
  calls per user request, regardless of how wide the resolved date
  range is. This is a deliberate simplification, documented in the
  method's own docstring, not a silent limitation.
- `_hotel_available_for()` (the pre-verification availability gate)
  now recognizes real-data records (`"available_from" not in hotel`)
  and always passes them through -- the live search call was already
  scoped to the requested dates, so there's no separate blackout/
  availability window to gate on the way the simulated dataset has.
- Hotel/flight record lookups (`_finalize`, the unsatisfiable path)
  used to read from `self.search_agent.hotels`/`.flights`, which only
  exist for simulated mode. Replaced with a request-scoped
  `self._last_hotels_by_id`/`_last_flights_by_id` cache populated by
  whichever candidate-queue builder ran, so both modes share the same
  lookup path.

**Frontend updated**: prefers a hotel's real `image_url` (a genuine
Google-hosted photo) over the local Picsum path when present, with an
`onerror` fallback that hides the `<img>` entirely rather than showing
a broken-image icon (real flight search returns no photos at all, and
some real hotel image URLs turned out not to load in one test run --
this fallback handles both gracefully). Added a distinct "not
verifiable" check-row style (gray "?" icon, "NOT VERIFIABLE" tag, no
fabricated comparison values) for `data_available: false` checks.
Fixed the front-desk-hours display line, which would have shown
"Desk closes null" for real hotels without a three-way branch.

**Verified end to end, twice, both through the real pipeline and
through the actual browser UI** (not mocked):
- `TravelAgent.run('Family of 4 to Austin, need a pool, 3 nights, Oct
  5-8, budget $2000 total')` -> real La Quinta Inn ($68/night, real
  pool amenity confirmed), real Frontier flight ($364/passenger),
  budget correctly computed at $1660 total from real prices, amenities
  check correctly passed against real free-text data, both
  arrival-vs-checkin and capacity correctly reported as
  not-verifiable rather than a false pass.
- Same request driven through the actual redesigned browser UI --
  screenshot-confirmed: real hotel/flight names and prices rendering,
  the green "Verified everything this data source could check..."
  headline with the two caveated checks correctly named, gray "NOT
  VERIFIABLE" tags rendering distinctly from the green pass rows, all
  matching what the backend actually computed.

**Bedrock calls this round**: 3 (2 `run()` calls + 1 browser-driven
test). **Running total: 71 + 3 = 74/80.**
**SerpApi calls this round**: 8 (2 direct verification + 2+2+2 across
the three end-to-end tests) -- worth keeping an eye on against the free
tier's monthly cap, no built-in usage tracking on this side yet.

**Still not done, flagged rather than silently skipped**: the Stage 3
battery (100% trap catch rate) was built entirely around the simulated
dataset's engineered traps and has NOT been re-run or re-validated
against real SerpApi data -- real listings won't have the same
purpose-built flaws, and 2 of the 4 checks are structurally
not-verifiable against this data source regardless of which listing
comes back. Whether/how to build an equivalent real-data battery (e.g.
scripted requests checking that real hidden-fee listings get caught by
the budget check, which IS fully real-data-capable) is an open
question for a future pass, not attempted here to conserve both
Bedrock and SerpApi free-tier budget this session.
