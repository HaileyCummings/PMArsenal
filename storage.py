"""Save and load trips as plain JSON files.

No database yet — each trip is just a file in data/trips/. That's enough to
let you close the browser and come back to a trip later, without adding
accounts or any real infrastructure.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from trip33.models import Constraint, ConstraintType, MustDo, Trip, Traveler

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "trips"


def new_trip_id() -> str:
    return uuid.uuid4().hex[:10]


def _parse_date(value: Optional[str]) -> Optional[date]:
    return date.fromisoformat(value) if value else None


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


def save_trip(trip: Trip, travelers: list[Traveler], constraints: list[Constraint], must_dos: list[MustDo]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "trip": {
            "id": trip.id,
            "destination": trip.destination,
            "start_date": trip.start_date.isoformat(),
            "end_date": trip.end_date.isoformat(),
            "traveler_count": trip.traveler_count,
            "budget_min": trip.budget_min,
            "budget_max": trip.budget_max,
            "pace_preference": trip.pace_preference,
            "avoids": trip.avoids,
        },
        "travelers": [
            {
                "id": t.id,
                "trip_id": t.trip_id,
                "name": t.name,
                "arrival_datetime": t.arrival_datetime.isoformat() if t.arrival_datetime else None,
                "departure_datetime": t.departure_datetime.isoformat() if t.departure_datetime else None,
            }
            for t in travelers
        ],
        "constraints": [
            {
                "id": c.id,
                "trip_id": c.trip_id,
                "type": c.type.value,
                "label": c.label,
                "start_time": c.start_time.isoformat() if c.start_time else None,
                "end_time": c.end_time.isoformat() if c.end_time else None,
                "recurrence_rule": c.recurrence_rule,
                "requires_full_group": c.requires_full_group,
                "is_chosen_absence": c.is_chosen_absence,
                "linked_dependency_id": c.linked_dependency_id,
                "resolved": c.resolved,
                "deadline": c.deadline.isoformat() if c.deadline else None,
            }
            for c in constraints
        ],
        "must_dos": [
            {
                "id": m.id,
                "trip_id": m.trip_id,
                "label": m.label,
                "flexible_placement": m.flexible_placement,
                "linked_constraint_id": m.linked_constraint_id,
            }
            for m in must_dos
        ],
    }
    (DATA_DIR / f"{trip.id}.json").write_text(json.dumps(payload, indent=2))


def load_trip(trip_id: str) -> tuple[Trip, list[Traveler], list[Constraint], list[MustDo]]:
    payload = json.loads((DATA_DIR / f"{trip_id}.json").read_text())

    t = payload["trip"]
    trip = Trip(
        id=t["id"],
        destination=t["destination"],
        start_date=_parse_date(t["start_date"]),
        end_date=_parse_date(t["end_date"]),
        traveler_count=t["traveler_count"],
        budget_min=t["budget_min"],
        budget_max=t["budget_max"],
        pace_preference=t["pace_preference"],
        avoids=t["avoids"],
    )
    travelers = [
        Traveler(
            id=x["id"], trip_id=x["trip_id"], name=x["name"],
            arrival_datetime=_parse_datetime(x["arrival_datetime"]),
            departure_datetime=_parse_datetime(x["departure_datetime"]),
        )
        for x in payload["travelers"]
    ]
    constraints = [
        Constraint(
            id=x["id"], trip_id=x["trip_id"], type=ConstraintType(x["type"]), label=x["label"],
            start_time=_parse_datetime(x["start_time"]), end_time=_parse_datetime(x["end_time"]),
            recurrence_rule=x["recurrence_rule"], requires_full_group=x["requires_full_group"],
            is_chosen_absence=x["is_chosen_absence"], linked_dependency_id=x["linked_dependency_id"],
            resolved=x["resolved"], deadline=_parse_datetime(x["deadline"]),
        )
        for x in payload["constraints"]
    ]
    must_dos = [
        MustDo(
            id=x["id"], trip_id=x["trip_id"], label=x["label"],
            flexible_placement=x["flexible_placement"], linked_constraint_id=x["linked_constraint_id"],
        )
        for x in payload["must_dos"]
    ]
    return trip, travelers, constraints, must_dos


def list_trips() -> list[dict]:
    if not DATA_DIR.exists():
        return []
    summaries = []
    for path in sorted(DATA_DIR.glob("*.json")):
        payload = json.loads(path.read_text())
        summaries.append({
            "id": payload["trip"]["id"],
            "destination": payload["trip"]["destination"],
            "start_date": payload["trip"]["start_date"],
            "end_date": payload["trip"]["end_date"],
        })
    return summaries
