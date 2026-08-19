# Travel booking dataset — design (Stage 1)

Simulated dataset for the multi-agent travel booking system. Fully synthetic —
no real travel APIs, no real hotel/airline names, no scraped data. Follows
the same philosophy as `mcp_firewall/servers/`: hand-crafted records with a
few deliberate traps, not randomly generated.

## Scope

- 3 destinations: Austin TX (`AUS`), Denver CO (`DEN`), Miami FL (`MIA`)
- Single origin: Chicago O'Hare (`ORD`) for every flight
- Trip window: October 2026
- 18 hotels (6 per destination), 18 flights (6 per destination)
- Data: [`data/hotels.json`](data/hotels.json), [`data/flights.json`](data/flights.json)
- Images: [`data/images/{hotels,flights}/`](data/images/) — 36 files, ~2.2MB, downloaded once via [`scripts/fetch_images.py`](scripts/fetch_images.py)

## Cost math (documented assumption, needs sign-off before Stage 2)

- `flight.price` is a **per-passenger** fare → multiply by party size.
- `hotel.price_per_night` + `hotel.resort_fee_per_night` are **per-room**, not
  per-guest, assuming the party fits in one room (`party_size <= max_occupancy`).
- `total_cost = flight.price * party_size + (hotel.price_per_night + hotel.resort_fee_per_night) * nights`

## Image source

Picsum (`picsum.photos/seed/<id>/800/600`) — no API key, no account, no
billing relationship, deterministic per-listing via seeded URLs. Downloaded
once to `data/images/` and referenced locally; never fetched live per search
and never passed to any agent as reasoning input, purely cosmetic in the UI.
(Chose this over Unsplash/Pexels APIs, which need the user to register their
own free developer account — asked first, user picked Picsum.)

## Trap listings (7 total) — the equivalent of the firewall project's "bob"

Each trap is a record that *looks* right on a surface field (a tag, a name,
a headline price) but fails on a deeper field the verification agent has to
actually read. The lesson carried over from the MCP firewall project: don't
trust the surface signal (a tag, a description, a name) as a proxy for the
real value — check the actual field that determines correctness.

| ID | Trap | Surface signal | Real value |
|---|---|---|---|
| `H-AUS-02` Riverside Inn Austin | Amenity tagged but unavailable | `amenities` includes `"pool"` | `amenity_notes.pool`: closed for renovation through Nov 2026 |
| `H-AUS-04` Austin Family Lodge | Name/tag implies family capacity | Named "Family Lodge", tagged `family_friendly` | `max_occupancy: 2` — fails any party of 3+ |
| `H-AUS-05` East Side Modern Hotel | Headline price looks in-budget | `price_per_night: 189` | `resort_fee_per_night: 35` (mandatory) pushes true nightly cost to 224 |
| `H-DEN-03` Downtown Denver Suites | Amenity tagged but inaccessible | `amenities` includes `"gym"` | `amenity_notes.gym`: relocated off-site, no guest access |
| `H-DEN-05` Cherry Creek Pet Friendly Hotel | Amenity tagged but seasonally suspended | `amenities` includes `"pet_friendly"` | `amenity_notes.pet_friendly`: suspended citywide for all of Oct 2026 (the trip's own window) |
| `H-MIA-03` Biscayne Bay Resort | Headline price looks in-budget | `price_per_night: 230` | `resort_fee_per_night: 45` (mandatory) pushes true nightly cost to 275 |
| `H-MIA-05` Wynwood Art Hotel | Amenity tagged but unavailable | `amenities` includes `"pool"` | `amenity_notes.pool`: closed for resurfacing, reopens Nov 1 2026 (after the whole trip window) |

Two flights also carry a **marketing-description trap** (description text
oversells the fare, structured `price` says otherwise) — not one of the
three named hard constraints, but a data-quality trap in the same spirit,
useful if a future agent is tempted to reason from `description` instead of
the structured `price` field:

| ID | Description says | Structured `price` says |
|---|---|---|
| `F-AUS-05` | "Marketed as our lowest fall fare — book now!" | `249` — actually the *most* expensive AUS option |
| `F-MIA-05` | "Advertised as an unbeatable low fare." | `175` — `F-MIA-03` at `135` is actually cheaper |

## Combination-only failures (no single record is "wrong")

Deliberately did **not** hand-craft artificial "combo trap" records for
this — real variance in the data produces genuine combination failures on
its own, which is more honest than manufacturing one:

- **Late/red-eye arrivals** vs **non-24hr front desks**: `F-AUS-03` (23:55),
  `F-AUS-06` (23:50), `F-DEN-06` (00:05, next day), `F-MIA-03` (01:15, next
  day) will all fail against `H-AUS-03` (desk closes 22:00), `H-DEN-02`
  (21:00), `H-MIA-02` (23:00), or `H-MIA-04` (20:00) — even though every one
  of those flights and hotels is individually a perfectly valid listing.
- **Budget-only-when-combined**: e.g. a cheap flight + a hotel that's each
  individually affordable can still blow the stated budget once
  `flight.price * party_size` is added to `nights * hotel.price_per_night`
  for a multi-night, multi-person trip — this is exactly why the check has
  to happen on the *combination*, not each leg in isolation.
- **Date/availability gaps**: `H-AUS-05` has a blackout Oct 19–21; flights
  `F-AUS-05`/`F-AUS-06` land on Oct 19, so that specific pairing is
  unavailable even though both records are independently fine — this also
  gives Stage 3 a genuinely "closest-option, can't fully satisfy" test case.

## Capacity as a fourth hard constraint (flagging, not deciding silently)

The original request's Stage 1 trap list named a capacity trap
(`H-AUS-04`, sleeps 2, marketed as family-friendly) but Stage 2's hard-check
list named only three checks: check-in-vs-arrival, budget, and amenities.
Recommend adding **party size vs. `max_occupancy`** as an explicit fourth
per-field check in the Verification Agent, since the dataset was built
assuming it's checked — otherwise `H-AUS-04` never gets caught by anything.
Will implement as check #4 in Stage 2 unless told otherwise.
