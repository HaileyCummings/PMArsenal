"""Belize — group trip with an unresolved pre-trip dependency.

What this test is really checking:
  - A must-do that needs the full group is never guessed at when one
    traveler's arrival is still unknown — it's held back, not placed.
  - The engine raises a clear, specific warning instead of a silent gap.
  - A full-day carve-out blocks all three day-parts, not just one.
"""
from datetime import date, datetime

from trip33.engine import generate_draft
from trip33.models import Constraint, ConstraintType, MustDo, Trip, Traveler

TRIP = Trip(
    id="trip_belize",
    destination="Belize",
    start_date=date(2026, 12, 2),
    end_date=date(2026, 12, 6),
    traveler_count=3,
    pace_preference="packed",
)

TRAVELERS = [
    Traveler(id="t_a", trip_id=TRIP.id, name="A",
             arrival_datetime=datetime(2026, 12, 2, 13, 0),
             departure_datetime=datetime(2026, 12, 6, 16, 0)),
    Traveler(id="t_b", trip_id=TRIP.id, name="B",
             arrival_datetime=datetime(2026, 12, 2, 13, 0),
             departure_datetime=datetime(2026, 12, 6, 16, 0)),
    Traveler(id="t_c", trip_id=TRIP.id, name="C",
             arrival_datetime=None,  # flight not booked yet
             departure_datetime=datetime(2026, 12, 5, 22, 0)),
]

DEP_FLIGHT = Constraint(
    id="c_dep_flight", trip_id=TRIP.id, type=ConstraintType.FLEXIBLE,
    label="C's flight booked", resolved=False,
    deadline=datetime(2026, 11, 20, 23, 59),
)
CAVE_TUBING_GATE = Constraint(
    id="c_group_cave", trip_id=TRIP.id, type=ConstraintType.GROUP_COMPLETENESS,
    label="Cave tubing (whole group)", requires_full_group=True,
    linked_dependency_id="c_dep_flight",
)
SNORKEL_TOUR = Constraint(
    id="c_snorkel", trip_id=TRIP.id, type=ConstraintType.FIXED_WINDOW,
    label="Snorkel tour",
    start_time=datetime(2026, 12, 4, 9, 0), end_time=datetime(2026, 12, 4, 13, 0),
)
RESORt_DAY = Constraint(
    id="c_resort_day", trip_id=TRIP.id, type=ConstraintType.PRIORITY_CARVEOUT,
    label="Unplanned resort day", is_chosen_absence=True,
    start_time=datetime(2026, 12, 5, 8, 0), end_time=datetime(2026, 12, 5, 23, 0),
)

CONSTRAINTS = [DEP_FLIGHT, CAVE_TUBING_GATE, SNORKEL_TOUR, RESORt_DAY]

MUST_DOS = [
    MustDo(id="md_cave", trip_id=TRIP.id, label="Cave tubing",
           flexible_placement=True, linked_constraint_id="c_group_cave"),
    MustDo(id="md_snorkel", trip_id=TRIP.id, label="Snorkel tour",
           flexible_placement=False, linked_constraint_id="c_snorkel"),
    MustDo(id="md_dinner", trip_id=TRIP.id, label="Sunset dinner"),
]


def _find_placements(draft: dict, label: str) -> list[tuple[str, str]]:
    hits = []
    for day, parts in draft.items():
        for part, info in parts.items():
            if any(item.get("label") == label for item in info["items"]):
                hits.append((day, part))
    return hits


def test_cave_tubing_is_never_placed_while_arrival_is_unknown():
    result = generate_draft(TRIP, TRAVELERS, CONSTRAINTS, MUST_DOS)
    placements = _find_placements(result["draft"], "Cave tubing")
    assert placements == []


def test_a_clear_warning_is_raised_instead_of_a_silent_gap():
    result = generate_draft(TRIP, TRAVELERS, CONSTRAINTS, MUST_DOS)
    warnings_text = " ".join(result["warnings"])
    assert "Cave tubing" in warnings_text
    assert "flight" in warnings_text.lower()


def test_snorkel_tour_lands_on_its_fixed_window():
    result = generate_draft(TRIP, TRAVELERS, CONSTRAINTS, MUST_DOS)
    friday_morning = result["draft"]["2026-12-04"]["morning"]
    assert friday_morning["status"] == "anchor"
    labels = [item["label"] for item in friday_morning["items"]]
    assert "Snorkel tour" in labels


def test_full_day_carveout_blocks_all_three_day_parts():
    result = generate_draft(TRIP, TRAVELERS, CONSTRAINTS, MUST_DOS)
    saturday = result["draft"]["2026-12-05"]
    for part in ("morning", "afternoon", "evening"):
        assert saturday[part]["status"] == "protected"

    dinner_spots = _find_placements(result["draft"], "Sunset dinner")
    assert len(dinner_spots) == 1
    assert dinner_spots[0][0] != "2026-12-05"