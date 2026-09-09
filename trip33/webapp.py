"""The constraint-intake form and the draft view — the first two Core
Screens from the spec, wired directly into the engine we already built.

Every form section below maps to one constraint type, but the person
filling it out never sees a word like "fixed_window" — they see plain
questions, and this file does the translation into Constraint/MustDo
objects behind the scenes.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time
from itertools import zip_longest
from typing import Optional

from flask import Flask, redirect, render_template, request, url_for

from trip33.engine import generate_draft
from trip33.models import Constraint, ConstraintType, MustDo, Trip, Traveler
from trip33.storage import list_trips, load_trip, new_trip_id, save_trip

app = Flask(__name__)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _parse_date(value: str) -> Optional[date]:
    return date.fromisoformat(value) if value else None


def _parse_datetime(date_value: str, time_value: str) -> Optional[datetime]:
    if not date_value:
        return None
    t = time.fromisoformat(time_value) if time_value else time(0, 0)
    return datetime.combine(date.fromisoformat(date_value), t)


def _rows(*lists):
    """Zip parallel form-field lists together, filling any short list with ''."""
    return zip_longest(*lists, fillvalue="")


@app.route("/")
def index():
    return render_template("index.html", trips=list_trips())


@app.route("/new", methods=["GET", "POST"])
def new_trip():
    if request.method == "GET":
        return render_template("new_trip.html")

    trip_id = new_trip_id()
    form = request.form

    avoids = [line.strip() for line in form.get("avoids", "").splitlines() if line.strip()]
    trip = Trip(
        id=trip_id,
        destination=form["destination"].strip(),
        start_date=_parse_date(form["start_date"]),
        end_date=_parse_date(form["end_date"]),
        traveler_count=1,
        budget_min=float(form["budget_min"]) if form.get("budget_min") else None,
        budget_max=float(form["budget_max"]) if form.get("budget_max") else None,
        pace_preference=form.get("pace_preference", "mix"),
        avoids=avoids,
    )

    travelers: list[Traveler] = []
    for name, a_date, a_time, d_date, d_time in _rows(
        form.getlist("traveler_name[]"),
        form.getlist("traveler_arrival_date[]"), form.getlist("traveler_arrival_time[]"),
        form.getlist("traveler_departure_date[]"), form.getlist("traveler_departure_time[]"),
    ):
        if not name.strip():
            continue
        travelers.append(Traveler(
            id=_new_id("trav"), trip_id=trip_id, name=name.strip(),
            arrival_datetime=_parse_datetime(a_date, a_time),
            departure_datetime=_parse_datetime(d_date, d_time),
        ))
    trip.traveler_count = len(travelers) or 1

    constraints: list[Constraint] = []
    must_dos: list[MustDo] = []

    # Recurring commitments (e.g. work hours)
    for label, frequency, start_t, end_t in _rows(
        form.getlist("recurring_label[]"), form.getlist("recurring_frequency[]"),
        form.getlist("recurring_start_time[]"), form.getlist("recurring_end_time[]"),
    ):
        if not label.strip() or not start_t or not end_t:
            continue
        constraints.append(Constraint(
            id=_new_id("con"), trip_id=trip_id, type=ConstraintType.RECURRING, label=label.strip(),
            recurrence_rule=f"{frequency}:{start_t}-{end_t}",
        ))

    # Fixed-time items (tickets, reservations, transport)
    for label, s_date, s_time, e_date, e_time, is_must_do in _rows(
        form.getlist("fixed_label[]"),
        form.getlist("fixed_start_date[]"), form.getlist("fixed_start_time[]"),
        form.getlist("fixed_end_date[]"), form.getlist("fixed_end_time[]"),
        form.getlist("fixed_is_must_do[]"),
    ):
        if not label.strip() or not s_date or not e_date:
            continue
        c = Constraint(
            id=_new_id("con"), trip_id=trip_id, type=ConstraintType.FIXED_WINDOW, label=label.strip(),
            start_time=_parse_datetime(s_date, s_time), end_time=_parse_datetime(e_date, e_time),
        )
        constraints.append(c)
        if is_must_do == "yes":
            must_dos.append(MustDo(
                id=_new_id("md"), trip_id=trip_id, label=label.strip(),
                flexible_placement=False, linked_constraint_id=c.id,
            ))

    # Protected / carve-out blocks
    for label, s_date, s_time, e_date, e_time in _rows(
        form.getlist("carveout_label[]"),
        form.getlist("carveout_start_date[]"), form.getlist("carveout_start_time[]"),
        form.getlist("carveout_end_date[]"), form.getlist("carveout_end_time[]"),
    ):
        if not label.strip() or not s_date or not e_date:
            continue
        constraints.append(Constraint(
            id=_new_id("con"), trip_id=trip_id, type=ConstraintType.PRIORITY_CARVEOUT, label=label.strip(),
            start_time=_parse_datetime(s_date, s_time), end_time=_parse_datetime(e_date, e_time),
            is_chosen_absence=True,
        ))

    # Must-dos that need the whole group present
    for label, waiting_on, deadline, still_waiting in _rows(
        form.getlist("group_mustdo_label[]"), form.getlist("group_mustdo_waiting_on[]"),
        form.getlist("group_mustdo_deadline[]"), form.getlist("group_mustdo_still_waiting[]"),
    ):
        if not label.strip():
            continue
        gate = Constraint(
            id=_new_id("con"), trip_id=trip_id, type=ConstraintType.GROUP_COMPLETENESS, label=label.strip(),
            requires_full_group=True,
        )
        if waiting_on.strip():
            dep = Constraint(
                id=_new_id("con"), trip_id=trip_id, type=ConstraintType.FLEXIBLE, label=waiting_on.strip(),
                resolved=(still_waiting != "yes"),
                deadline=_parse_datetime(deadline, "23:59") if deadline else None,
            )
            constraints.append(dep)
            gate.linked_dependency_id = dep.id
        constraints.append(gate)
        must_dos.append(MustDo(
            id=_new_id("md"), trip_id=trip_id, label=label.strip(),
            flexible_placement=True, linked_constraint_id=gate.id,
        ))

    # Everything else — fully flexible must-dos
    for label in form.getlist("flexible_mustdo_label[]"):
        if not label.strip():
            continue
        must_dos.append(MustDo(id=_new_id("md"), trip_id=trip_id, label=label.strip()))

    save_trip(trip, travelers, constraints, must_dos)
    return redirect(url_for("view_trip", trip_id=trip_id))


@app.route("/trip/<trip_id>")
def view_trip(trip_id: str):
    trip, travelers, constraints, must_dos = load_trip(trip_id)
    result = generate_draft(trip, travelers, constraints, must_dos)
    return render_template("draft.html", trip=trip, result=result)


if __name__ == "__main__":
    app.run(debug=True)
