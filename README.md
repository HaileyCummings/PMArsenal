# 33 — Trip Planning Engine (First Build Sprint)

This is the smallest slice of the app that tests the core idea: can a program
take a trip's constraints as input and produce a day-by-day draft a human
trip planner would actually make by hand?

**What's in here:** the four data objects (Trip, Traveler, Constraint,
MustDo) and the draft-placement engine. **What's not in here:** any booking
integration, payments, accounts, or screens — that's all intentionally
deferred to later sprints.

## How to look at this without reading code

- `trip33/models.py` — the four data objects, matching the spec's "First
  Build Sprint" section field-for-field, plus two small additions (see
  below).
- `trip33/engine.py` — the actual placement logic. The comment at the top
  of the file explains the six steps in plain language.
- `tests/` — three test cases, one per real trip from the spec (Miami
  Carnival, Vancouver, Belize). Each one is a realistic set of constraints
  plus a check that the engine handled the tricky part of that trip
  correctly. These double as the "does it match what a human PM would do"
  regression tests the spec calls for.

## How to run the tests

```
pip install -r requirements.txt
pytest -v
```

`-v` prints each test's name and a pass/fail — useful for seeing which
scenario (if any) breaks after a change.

## Two small additions beyond the spec's literal field list

The spec's object definitions didn't include everything needed to make
pre-trip dependency tracking (constraint type #5) actually work, so two
fields were added:

1. **`Constraint.resolved`** (true/false) — whether a pending pre-trip task
   (like "flight booked" or "payment cleared") has actually happened yet.
2. **`Constraint.deadline`** — when that task needed to resolve by, used
   only for the warning message, not for scheduling.

Also added: **`MustDo.linked_constraint_id`** — lets a must-do point at the
constraint it's really tied to, for the "this must-do is secretly a
fixed_window or group_completeness constraint" case the spec describes
(e.g., "Costume pickup" is a must-do, but its real timing comes from a
fixed_window constraint).

## Three decisions made while building (flagged for review)

These came up as genuine ambiguities in the spec's 6-step ordering and were
resolved based on what you confirmed when reviewing the test cases:

1. **Priority carve-outs are reserved before anything else is placed**, not
   placed-then-evicted. The spec listed this as step 5, but reserving it as
   step 0 means a must-do never even considers a protected block, rather
   than getting placed there and then having to be moved.
2. **Group-completeness is a placement filter, not a post-hoc check.** A
   must-do that needs the full group only becomes a candidate for a block
   once every traveler's arrival is confirmed and has passed for that
   block — it's never placed and then flagged as wrong.
3. **An unresolved pre-trip dependency means the linked item is left off
   the draft entirely**, with a specific warning explaining why — not
   placed provisionally and hoped for.

## One simplification worth knowing about

The draft works in three chunks per day — morning, afternoon, evening —
rather than minute-by-minute. This matches the spec's "day-by-day draft"
output and keeps the placement logic easy to follow and test. It can be
made finer-grained later without changing the overall approach; nothing
here depends on the three-chunk assumption in a way that would make that
hard.

## What "relative slack" means in code

The spec describes ranking free blocks by how many constraints were
"relieved" to make them free. This build implements a concrete version of
that: a block loses a point if something fixed sits immediately before it,
and another point if something fixed sits immediately after it. A block
with nothing pressing on either side scores highest and gets first pick of
must-dos. It's a reasonable starting heuristic, not the final word — easy
to make smarter later (e.g. factoring in how "heavy" the neighboring event
was) once there's real usage to learn from.
