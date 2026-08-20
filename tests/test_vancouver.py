"""Vancouver — solo work trip.

What this test is really checking:
  - Recurring work hours anchor every weekday, automatically.
  - A protected rest evening is respected.
  - Flexible must-dos (hike, restaurant) land somewhere that isn't work,
    the client dinner, or the protected evening.
"""
from datetime import date, datetime

from trip33.engine import generate_draft
from trip33.models import Constraint, ConstraintType, MustDo, Trip, Traveler

TRIP = Trip(
    id="trip_vancouver",
    destination="Vancouver",
    start_date=date(2026, 9, 13),
    end_date=date(2026, 9, 18),
    traveler_count=1,
    pace_preference="chill",
    avoids=["no super late nights"],
)

TRAVELERS = [
    Traveler(id="t_solo", trip_id=TRIP.id, name="Solo traveler",
             arrival_datetime=datetime(2026, 9, 13, 19, 0),
             departure_datetime=datetime(2026, 9, 18, 21, 0)),
]

WORK_HOURS = Constraint(
    id="c_work", trip_id=TRIP.id, type=ConstraintType.RECURRING,
    label="Work hours", recurrence_rule="weekday:09:00-17:00",
)
CLIENT_DINNER = Constraint(
    id="c_dinner", trip_id=TRIP.id, type=ConstraintType.FIXED_WINDOW,
    label="Client dinner",
    start_time=datetime(2026, 9, 15, 19, 0), end_time=datetime(2026, 9, 15, 21, 0),
)
FLIGHT_HOME = Constraint(
    id="c_flight", trip_id=TRIP.id, type=ConstraintType.FIXED_WINDOW,
    label="Flight home",
    start_time=datetime(2026, 9, 18, 21, 0), end_time=datetime(2026, 9, 18, 22, 0),
)
REST_EVENING = Constraint(
    id="c_rest", trip_id=TRIP.id, type=ConstraintType.PRIORITY_CARVEOUT,
    label="Rest evening", is_chosen_absence=True,
    start_time=datetime(2026, 9, 17, 18, 0), end_time=datetime(2026, 9, 17, 22, 0),
)

CONSTRAINTS = [WORK_HOURS, CLIENT_DINNER, FLIGHT_HOME, REST_EVENING]

MUST_DOS = [
    MustDo(id="md_hike", trip_id=TRIP.id, label="Hike"),
    MustDo(id="md_restaurant", trip_id=TRIP.id, label="Try the restaurant"),
]


def _find_placements(draft: dict, label: str) -> list[tuple[str, str]]:
    hits = []
    for day, parts in draft.items():
        for part, info in parts.items():
            if any(item.get("label") == label for item in info["items"]):
                hits.append((day, part))
    return hits


def test_work_hours_anchor_every_weekday_automatically():
    result = generate_draft(TRIP, TRAVELERS, CONSTRAINTS, MUST_DOS)
    draft = result["draft"]

    for day_str, parts in draft.items():
        d = date.fromisoformat(day_str)
        if d.weekday() < 5:  # Mon-Fri
            assert parts["morning"]["status"] == "anchor"
            assert parts["afternoon"]["status"] == "anchor"


def test_rest_evening_is_protected():
    result = generate_draft(TRIP, TRAVELERS, CONSTRAINTS, MUST_DOS)
    draft = result["draft"]
    assert draft["2026-09-17"]["evening"]["status"] == "protected"


def test_flexible_must_dos_avoid_work_dinner_and_rest_evening():
    result = generate_draft(TRIP, TRAVELERS, CONSTRAINTS, MUST_DOS)
    draft = result["draft"]

    hike_spots = _find_placements(draft, "Hike")
    restaurant_spots = _find_placements(draft, "Try the restaurant")
    assert len(hike_spots) == 1
    assert len(restaurant_spots) == 1

    for day, part in hike_spots + restaurant_spots:
        assert (day, part) != ("2026-09-17", "evening")
        assert (day, part) != ("2026-09-15", "evening")  # client dinner
        d = date.fromisoformat(day)
        if d.weekday() < 5 and part in ("morning", "afternoon"):
            raise AssertionError(f"must-do landed during work hours: {day} {part}")