"""Draft-placement engine — the "First Build Sprint" logic from the spec.

Plain-language summary of the order this follows (this is the part that
turns raw constraints into a day-by-day draft):

  0. Reserve every priority_carveout block first. Nothing else is ever
     allowed to touch it. (This resolves an ordering question in the spec:
     rather than placing things and evicting them later, protected blocks
     are taken off the table before anything else is placed.)
  1. Place fixed_window and recurring constraints as anchors on the
     calendar. These are non-negotiable.
  2. Score every remaining open block by "relative slack" — how free it
     really is, based on what's near it.
  3. Place must-dos into the highest-slack blocks first. A must-do that
     needs the full group is only eligible for a block once every
     traveler's arrival is confirmed and has passed — if that never
     happens (or the arrival is still unknown), it's held back rather than
     guessed at.
  4. Sweep for unresolved pre-trip dependencies and attach a clear warning
     to anything that's blocked on one, instead of a silent gap.

Day-by-day granularity: each day is split into three parts — morning
(8am-12pm), afternoon (12pm-6pm), evening (6pm-11pm). This is coarser than
minute-by-minute scheduling, but it matches the spec's "day-by-day draft"
output and keeps the logic easy to follow. Can be made finer later without
changing the overall approach.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional

from trip33.models import Constraint, ConstraintType, MustDo, Trip, Traveler

DAY_PARTS = [
    ("morning", time(8, 0), time(12, 0)),
    ("afternoon", time(12, 0), time(18, 0)),
    ("evening", time(18, 0), time(23, 0)),
]


@dataclass
class Block:
    day: date
    part: str  # "morning" | "afternoon" | "evening"
    start: datetime
    end: datetime
    status: str = "open"  # "open" | "protected" | "anchor" | "placed"
    items: list[dict] = field(default_factory=list)

    @property
    def key(self) -> tuple[date, str]:
        return (self.day, self.part)


def _dates_in_range(start: date, end: date) -> list[date]:
    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    return days


def _build_skeleton(trip: Trip) -> list[Block]:
    blocks = []
    for d in _dates_in_range(trip.start_date, trip.end_date):
        for part_name, start_t, end_t in DAY_PARTS:
            blocks.append(
                Block(
                    day=d,
                    part=part_name,
                    start=datetime.combine(d, start_t),
                    end=datetime.combine(d, end_t),
                )
            )
    return blocks


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and a_end > b_start


def _blocks_overlapping(blocks: list[Block], start: datetime, end: datetime) -> list[Block]:
    return [b for b in blocks if _overlaps(b.start, b.end, start, end)]


def _expand_recurring(constraint: Constraint, trip: Trip) -> list[tuple[datetime, datetime]]:
    """Turn a recurrence_rule like 'weekday:09:00-17:00' or 'daily:09:00-17:00'
    into concrete (start, end) datetimes across the trip's date range."""
    if not constraint.recurrence_rule:
        return []
    frequency, _, time_range = constraint.recurrence_rule.partition(":")
    start_str, _, end_str = time_range.partition("-")
    start_t = time.fromisoformat(start_str)
    end_t = time.fromisoformat(end_str)

    occurrences = []
    for d in _dates_in_range(trip.start_date, trip.end_date):
        if frequency == "weekday" and d.weekday() >= 5:  # Sat/Sun
            continue
        occurrences.append((datetime.combine(d, start_t), datetime.combine(d, end_t)))
    return occurrences


def _reserve_carveouts(blocks: list[Block], constraints: list[Constraint]) -> None:
    for c in constraints:
        if c.type != ConstraintType.PRIORITY_CARVEOUT or not c.start_time or not c.end_time:
            continue
        for block in _blocks_overlapping(blocks, c.start_time, c.end_time):
            block.status = "protected"
            block.items.append({"label": c.label, "type": "priority_carveout", "chosen_absence": c.is_chosen_absence})


def _place_anchors(blocks: list[Block], constraints: list[Constraint], trip: Trip) -> None:
    for c in constraints:
        if c.type == ConstraintType.FIXED_WINDOW and c.start_time and c.end_time:
            occurrences = [(c.start_time, c.end_time)]
        elif c.type == ConstraintType.RECURRING:
            occurrences = _expand_recurring(c, trip)
        else:
            continue

        for occ_start, occ_end in occurrences:
            for block in _blocks_overlapping(blocks, occ_start, occ_end):
                if block.status == "protected":
                    continue  # a carve-out always wins, even over an anchor
                block.status = "anchor"
                block.items.append({"label": c.label, "type": c.type.value, "constraint_id": c.id})


def _score_slack(blocks: list[Block]) -> dict[tuple[date, str], int]:
    """Higher score = more free. Looks at whether an anchor block sits right
    before or right after this one — that's the 'what did this block get
    relieved of' idea from the spec."""
    by_key = {b.key: b for b in blocks}
    ordered = sorted(blocks, key=lambda b: b.start)
    index_by_key = {b.key: i for i, b in enumerate(ordered)}

    scores = {}
    for b in ordered:
        if b.status != "open":
            continue
        pressure = 0
        i = index_by_key[b.key]
        if i + 1 < len(ordered) and ordered[i + 1].status == "anchor":
            pressure += 1  # something looms right after this block
        if i - 1 >= 0 and ordered[i - 1].status == "anchor":
            pressure += 1  # this block follows right on the heels of something
        scores[b.key] = 2 - pressure
    return scores


def _all_travelers_present(travelers: list[Traveler], at: datetime) -> bool:
    for t in travelers:
        if t.arrival_datetime is None or t.arrival_datetime > at:
            return False
        if t.departure_datetime is not None and t.departure_datetime <= at:
            return False
    return True


def _dependency_resolved(constraint_id: Optional[str], constraints_by_id: dict[str, Constraint]) -> bool:
    if constraint_id is None:
        return True
    target = constraints_by_id.get(constraint_id)
    return target.resolved if target else True


def _place_must_dos(
    blocks: list[Block],
    must_dos: list[MustDo],
    constraints_by_id: dict[str, Constraint],
    travelers: list[Traveler],
    slack_scores: dict[tuple[date, str], int],
) -> list[dict]:
    warnings = []
    ordered_open = sorted(
        [b for b in blocks if b.status == "open"],
        key=lambda b: (-slack_scores.get(b.key, 0), b.start),
    )

    for md in must_dos:
        linked = constraints_by_id.get(md.linked_constraint_id) if md.linked_constraint_id else None

        # Case A: this must-do is really a fixed_window in disguise — it was
        # already anchored in step 1, just note it's the must-do satisfying it.
        if linked and linked.type == ConstraintType.FIXED_WINDOW:
            for block in blocks:
                if any(item.get("constraint_id") == linked.id for item in block.items):
                    block.items.append({"label": md.label, "type": "must_do", "satisfies": linked.id})
            continue

        # Case B: this must-do needs the full group present.
        if linked and linked.type == ConstraintType.GROUP_COMPLETENESS:
            if not _dependency_resolved(linked.linked_dependency_id, constraints_by_id):
                warnings.append(
                    f"'{md.label}' is blocked — its dependency "
                    f"('{constraints_by_id[linked.linked_dependency_id].label}') hasn't resolved"
                    + (f" (deadline was {constraints_by_id[linked.linked_dependency_id].deadline})"
                       if constraints_by_id[linked.linked_dependency_id].deadline else "")
                    + ", so it can't be placed yet."
                )
                continue

            placed = False
            for block in ordered_open:
                if _all_travelers_present(travelers, block.start):
                    block.status = "placed"
                    block.items.append({"label": md.label, "type": "must_do", "requires_full_group": True})
                    ordered_open.remove(block)
                    placed = True
                    break
            if not placed:
                warnings.append(
                    f"'{md.label}' needs everyone present, but no open block in the trip "
                    "has the full group confirmed and available — it's not on the draft."
                )
            continue

        # Case C: a plain flexible must-do — take the highest-slack open block.
        if not ordered_open:
            warnings.append(f"'{md.label}' couldn't be placed — no open blocks left in the trip.")
            continue
        block = ordered_open.pop(0)
        block.status = "placed"
        block.items.append({"label": md.label, "type": "must_do"})

    return warnings


def _dependency_sweep(constraints: list[Constraint], constraints_by_id: dict[str, Constraint]) -> list[str]:
    warnings = []
    for c in constraints:
        if c.linked_dependency_id and not _dependency_resolved(c.linked_dependency_id, constraints_by_id):
            target = constraints_by_id[c.linked_dependency_id]
            msg = f"'{c.label}' depends on '{target.label}', which hasn't resolved yet"
            if target.deadline:
                msg += f" (deadline was {target.deadline})"
            warnings.append(msg + ".")
    return warnings


def generate_draft(
    trip: Trip,
    travelers: list[Traveler],
    constraints: list[Constraint],
    must_dos: list[MustDo],
) -> dict:
    blocks = _build_skeleton(trip)
    constraints_by_id = {c.id: c for c in constraints}

    _reserve_carveouts(blocks, constraints)                  # step 0
    _place_anchors(blocks, constraints, trip)                 # step 1
    slack_scores = _score_slack(blocks)                       # step 2
    must_do_warnings = _place_must_dos(                        # step 3
        blocks, must_dos, constraints_by_id, travelers, slack_scores
    )
    dependency_warnings = _dependency_sweep(constraints, constraints_by_id)  # step 4

    draft: dict[str, dict] = {}
    for b in sorted(blocks, key=lambda b: b.start):
        day_key = b.day.isoformat()
        draft.setdefault(day_key, {})
        draft[day_key][b.part] = {
            "status": b.status,
            "items": b.items,
            "slack_score": slack_scores.get(b.key),
        }

    all_warnings = must_do_warnings + dependency_warnings
    return {"draft": draft, "warnings": all_warnings}
