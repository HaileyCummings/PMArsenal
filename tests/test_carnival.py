"""Miami Carnival — group trip, staggered arrivals/departures.

What this test is really checking:
  - A protected (priority_carveout) block never gets a must-do placed in it,
    even though it would otherwise be the emptiest, most attractive block
    in the whole trip.
  - A must-do that needs the full group only lands on a day everyone is
    actually there.
"""
from datetime import date, datetime

from trip33.engine import generate_draft
from trip33.models import Constraint, ConstraintType, MustDo, Trip, Traveler

TRIP = Trip(
    id="trip_carnival",
    destination="Miami",
    start_date=date(2026, 10, 8),
    end_date=date(2026, 10, 12),
    traveler_count=4,
    pace_preference="mix",
    avoids=["no super early mornings"],
)

TRAVELERS = [
    Traveler(id="t_organizer", trip_id=TRIP.id, name="Organizer",
             arrival_datetime=datetime(2026, 10, 8, 10, 0),
             departure_datetime=datetime(2026, 10, 12, 18, 0)),
    Traveler(id="t_b", trip_id=TRIP.id, name="B",
             arrival_datetime=datetime(2026, 10, 8, 14, 0),
             departure_datetime=datetime(2026, 10, 12, 18, 0)),
    Traveler(id="t_c", trip_id=TRIP.id, name="C",
             arrival_datetime=datetime(2026, 10, 9, 21, 0),
             departure_datetime=datetime(2026, 10, 11, 23, 0)),
    Traveler(id="t_d", trip_id=TRIP.id, name="D",
             arrival_datetime=datetime(2026, 10, 9, 11, 0),
             departure_datetime=datetime(2026, 10, 12, 18, 0)),
]

DEP_PAYMENT = Constraint(
    id="c_dep_payment", trip_id=TRIP.id, type=ConstraintType.FLEXIBLE,
    label="Costume payment cleared", resolved=True,
    deadline=datetime(2026, 10, 7, 23, 59),
)
COSTUME_PICKUP = Constraint(
    id="c_pickup", trip_id=TRIP.id, type=ConstraintType.FIXED_WINDOW,
    label="Costume pickup",
    start_time=datetime(2026, 10, 9, 12, 0), end_time=datetime(2026, 10, 9, 16, 0),
    linked_dependency_id="c_dep_payment",
)
RECOVERY_MORNING = Constraint(
    id="c_recovery", trip_id=TRIP.id, type=ConstraintType.PRIORITY_CARVEOUT,
    label="Recovery morning", is_chosen_absence=True,
    start_time=datetime(2026, 10, 11, 8, 0), end_time=datetime(2026, 10, 11, 12, 0),
)
GROUP_BEACH_GATE = Constraint(
    id="c_group_beach", trip_id=TRIP.id, type=ConstraintType.GROUP_COMPLETENESS,
    label="Group Beach Day", requires_full_group=True,
)

CONSTRAINTS = [DEP_PAYMENT, COSTUME_PICKUP, RECOVERY_MORNING, GROUP_BEACH_GATE]

MUST_DOS = [
    MustDo(id="md_pickup", trip_id=TRIP.id, label="Costume pickup",
           flexible_placement=False, linked_constraint_id="c_pickup"),
    MustDo(id="md_group_beach", trip_id=TRIP.id, label="Group Beach Day",
           flexible_placement=True, linked_constraint_id="c_group_beach"),
    MustDo(id="md_market", trip_id=TRIP.id, label="Farmers market visit",
           flexible_placement=True),
]


def _find_placements(draft: dict, label: str) -> list[tuple[str, str]]:
    hits = []
    for day, parts in draft.items():
        for part, info in parts.items():
            if any(item.get("label") == label for item in info["items"]):
                hits.append((day, part))
    return hits


def test_carveout_is_never_used_even_though_it_is_the_emptiest_block():
    result = generate_draft(TRIP, TRAVELERS, CONSTRAINTS, MUST_DOS)
    draft = result["draft"]

    sunday_morning = draft["2026-10-11"]["morning"]
    assert sunday_morning["status"] == "protected"

    market_placements = _find_placements(draft, "Farmers market visit")
    assert len(market_placements) == 1
    assert market_placements[0] != ("2026-10-11", "morning")


def test_costume_pickup_lands_on_the_fixed_window():
    result = generate_draft(TRIP, TRAVELERS, CONSTRAINTS, MUST_DOS)
    draft = result["draft"]
    friday_afternoon = draft["2026-10-09"]["afternoon"]
    assert friday_afternoon["status"] == "anchor"
    labels = [item["label"] for item in friday_afternoon["items"]]
    assert "Costume pickup" in labels


def test_group_beach_day_only_placed_when_everyone_is_actually_there():
    result = generate_draft(TRIP, TRAVELERS, CONSTRAINTS, MUST_DOS)
    draft = result["draft"]

    placements = _find_placements(draft, "Group Beach Day")
    assert len(placements) == 1
    day, part = placements[0]

    # Not before C arrives (Fri 10/9 9pm), not after C leaves (Sun 10/11 11pm),
    # and never in the protected Sunday morning block.
    assert day not in ("2026-10-08", "2026-10-09", "2026-10-12")
    assert (day, part) != ("2026-10-11", "morning")


def test_no_dependency_warnings_since_payment_already_cleared():
    result = generate_draft(TRIP, TRAVELERS, CONSTRAINTS, MUST_DOS)
    assert result["warnings"] == []