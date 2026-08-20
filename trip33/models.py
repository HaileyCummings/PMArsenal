"""Core data objects for the 33 trip-planning engine.

These follow the "First Build Sprint" section of the spec. Two small fields
are added beyond the spec's literal list, both needed to make pre-trip
dependency tracking actually work end to end — see README.md for why.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


class ConstraintType(str, Enum):
    FLEXIBLE = "flexible"                    # #1
    FIXED_WINDOW = "fixed_window"            # #2
    GROUP_COMPLETENESS = "group_completeness"  # #3
    RECURRING = "recurring"                  # #6
    RELATIVE_SLACK = "relative_slack"        # #7 — computed, not user-entered
    PRIORITY_CARVEOUT = "priority_carveout"  # #10
    MULTI_ORIGIN_EXIT = "multi_origin_exit"  # #11


@dataclass
class Trip:
    id: str
    destination: str
    start_date: date
    end_date: date
    traveler_count: int
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    pace_preference: str = "mix"  # "chill" | "mix" | "packed"
    avoids: list[str] = field(default_factory=list)


@dataclass
class Traveler:
    id: str
    trip_id: str
    name: str
    arrival_datetime: Optional[datetime] = None
    departure_datetime: Optional[datetime] = None


@dataclass
class Constraint:
    id: str
    trip_id: str
    type: ConstraintType
    label: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    recurrence_rule: Optional[str] = None  # e.g. "weekday:09:00-17:00"
    requires_full_group: bool = False
    is_chosen_absence: bool = False
    linked_dependency_id: Optional[str] = None

    # Addition beyond the spec: a pre-trip dependency has to know whether the
    # thing it depends on has actually happened, and by when it needed to.
    # Without these two fields there's nothing for the engine to check.
    resolved: bool = True
    deadline: Optional[datetime] = None


@dataclass
class MustDo:
    id: str
    trip_id: str
    label: str
    flexible_placement: bool = True

    # Addition beyond the spec: lets a must-do borrow its timing or its
    # group-completeness gate from a constraint, for the "this must-do is
    # really a fixed_window/group_completeness constraint in disguise" case
    # the spec describes.
    linked_constraint_id: Optional[str] = None