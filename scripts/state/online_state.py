#!/usr/bin/env python3
"""The state an in-flight executor can actually derive, and nothing more.

The Stage 2 core actions are written as preconditions over the semantic state
in `scripts/state/semantic_state.py`.  That state is folded from the closed
trace, which is assembled after the flight from the ULog, the sidecars and the
clock bridge.  An executor choosing its next action while the aircraft is still
flying has none of that.  It has the workload and runner lifecycle sidecars as
they are appended, and the telemetry sidecar.

This module writes down what those in-flight sources support.  Three rules keep
it honest:

* It is a proxy, not evidence.  Nothing derived here enters the trace, the
  evidence Gate or an Oracle.  It only decides which action the tester takes
  next.  The closed trace remains the sole account of what the system did.
* It never claims an unobservable field.  The command lineage is reconstructed
  from ULog subject identity, so in flight it is reported as `unobservable`
  rather than assumed complete.  Every online gate is therefore a weakening of
  the offline precondition it stands for, not an equivalent of it.
* Because it is a weakening, its adequacy is measured rather than asserted.
  `scripts/corpus/online_state_check.py` replays both projections over the same
  retained attempt and reports every interval where an online gate held while
  the offline precondition did not.

The vehicle's declared navigation mode is an input here, which the route model
refuses as evidence of route identity.  That is precisely why this is a proxy
whose divergence is measured: in flight there is no Runtime Route Instance to
follow, and the replay reports what the shortcut costs rather than assuming it
costs nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping, Sequence

from scripts.state.semantic_state import (
    EXTERNAL_FAMILIES,
    SAFE_ROUTES,
    SemanticStateError,
    route_family,
)


class OnlineStateError(ValueError):
    """In-flight evidence cannot be folded into a deterministic online state."""


# The producer's own confirmation that the tested route took over.
ACTIVE_KINDS = frozenset({"offboard_observed_active", "dynamic_mode_observed_active"})
# AUTO_LOITER, AUTO_RTL, AUTO_LAND.  The three internal safe routes this study
# configures, recognised by the only identity telemetry offers in flight.
SAFE_NAV_STATES = frozenset({4, 5, 18})
# NAVIGATION_STATE_OFFBOARD.  The dynamic mechanism has no fixed value: its
# navigation state is the mode identifier PX4 returns when the external mode
# registers, which the producer records for itself.
OFFBOARD_NAV_STATE = 14
AUTHORITY_FAMILIES = (
    "unknown",
    "internal_navigator",
    "internal_safe",
    "external_offboard",
    "external_dynamic",
)
ACTIVATION_STATES = ("none", "requested", "active", "rejected")
REGISTRATION_STATES = ("none", "accepted", "rejected")
FAULT_CLASSES = ("none", "setpoint_stall", "health_loss", "process_exit", "other")
# The lineage is reconstructed from ULog subject identity, so no in-flight
# source establishes it.  It is named rather than left out, so a gate that
# needs it has to say so instead of quietly ignoring it.
UNOBSERVABLE_LINEAGE = "unobservable"


def _fault_class(reason: str) -> str:
    """Classify a fault the way the offline fold does, from the same text."""

    lowered = reason.lower()
    if "stall" in lowered:
        return "setpoint_stall"
    if "health" in lowered:
        return "health_loss"
    if "exit" in lowered or "process" in lowered:
        return "process_exit"
    return "other"


@dataclass(frozen=True)
class OnlineState:
    """One state of the tested authority path as the flight can observe it."""

    # Who holds authority, as the best in-flight source reports it.  This
    # stands in for the offline route family, which is read from Runtime Route
    # Instance identity that no in-flight source carries.
    authority_family: str = "unknown"
    tested_route_active: bool = False
    producer_session: str | None = None
    activation_cycle: int | None = None
    activation_state: str = "none"
    registration_state: str = "none"
    # Always unobservable; kept so a gate cannot silently drop it.
    lineage: str = UNOBSERVABLE_LINEAGE
    fault_class: str = "none"
    fault_observed: bool = False
    completion_observed: bool = False
    successor_requested_route: str | None = None
    successor_installed: bool = False
    fallback_route: str | None = None
    fallback_installed: bool = False
    motion_entered: bool = False
    motion_completed: bool = False
    airborne: bool = False
    terminal: bool = False

    @property
    def holds_authority(self) -> bool:
        """Some route was observed holding authority and the episode is live."""

        return self.authority_family != "unknown" and not self.terminal

    @property
    def external_authority(self) -> bool:
        return self.authority_family in EXTERNAL_FAMILIES and not self.terminal

    @property
    def internal_authority(self) -> bool:
        return (
            self.authority_family in ("internal_safe", "internal_navigator")
            and not self.terminal
        )

    @property
    def internal_safe_authority(self) -> bool:
        return self.authority_family == "internal_safe" and not self.terminal

    def key(self) -> str:
        """Bounded classification of this state, for comparison and coverage."""

        return "|".join(
            (
                f"authority={self.authority_family}",
                f"activation={self.activation_state}",
                f"registration={self.registration_state}",
                f"fault={self.fault_class}",
                f"completion={'yes' if self.completion_observed else 'no'}",
                f"successor={'installed' if self.successor_installed else ('requested' if self.successor_requested_route else 'none')}",
                f"fallback={'installed' if self.fallback_installed else ('triggered' if self.fallback_route else 'none')}",
                f"motion={'completed' if self.motion_completed else ('entered' if self.motion_entered else 'none')}",
                f"terminal={'yes' if self.terminal else 'no'}",
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "authority_family": self.authority_family,
            "tested_route_active": self.tested_route_active,
            "producer_session": self.producer_session,
            "activation_cycle": self.activation_cycle,
            "activation_state": self.activation_state,
            "registration_state": self.registration_state,
            "lineage": self.lineage,
            "fault_class": self.fault_class,
            "fault_observed": self.fault_observed,
            "completion_observed": self.completion_observed,
            "successor_requested_route": self.successor_requested_route,
            "successor_installed": self.successor_installed,
            "fallback_route": self.fallback_route,
            "fallback_installed": self.fallback_installed,
            "motion_entered": self.motion_entered,
            "motion_completed": self.motion_completed,
            "airborne": self.airborne,
            "terminal": self.terminal,
        }


@dataclass(frozen=True)
class OnlineStep:
    """One folded observation and the state that follows it."""

    monotonic_ns: int
    kind: str
    state: OnlineState


def _external_family(mechanism: str) -> str:
    family = route_family(mechanism)
    if family not in EXTERNAL_FAMILIES:
        raise OnlineStateError(f"the tested route is not an external route: {mechanism}")
    return family


def merge_records(*sources: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Every in-flight record in one monotonic order.

    The sidecars are appended independently by separate processes, so the
    executor sees them interleaved by arrival time.  A record without an
    arrival time cannot be placed in that order and is refused rather than
    guessed into position.
    """

    merged: list[dict[str, Any]] = []
    for source in sources:
        for record in source:
            if not isinstance(record, Mapping):
                raise OnlineStateError("an in-flight record is not an object")
            moment = record.get("received_monotonic_ns")
            if not isinstance(moment, int) or isinstance(moment, bool):
                raise OnlineStateError(
                    f"an in-flight {record.get('kind')} record has no arrival time"
                )
            merged.append(dict(record))
    # Stable on arrival time; ties keep the order the sources were given in, so
    # the fold is a pure function of its inputs.
    merged.sort(key=lambda value: int(value["received_monotonic_ns"]))
    return merged


def _fold_lifecycle(state: OnlineState, record: Mapping[str, Any], *, external: str) -> OnlineState:
    kind = str(record.get("kind"))
    if kind in ACTIVE_KINDS:
        cycle = record.get("cycle")
        return replace(
            state,
            authority_family=external,
            tested_route_active=True,
            activation_state="active",
            activation_cycle=int(cycle) if isinstance(cycle, int) else state.activation_cycle,
        )
    if kind in ("transition_requested", "activation_requested", "offboard_requested"):
        target = record.get("target_route")
        if isinstance(target, str):
            try:
                family = route_family(target)
            except SemanticStateError as exc:
                raise OnlineStateError(str(exc)) from exc
            if family not in EXTERNAL_FAMILIES:
                # A request away from the tested route is not an activation of
                # it, so it must not advance the activation state.
                return state
        return replace(state, activation_state="requested")
    if kind == "producer_session_started":
        session = record.get("producer_session")
        cycle = record.get("cycle")
        return replace(
            state,
            producer_session=str(session) if session is not None else state.producer_session,
            activation_cycle=int(cycle) if isinstance(cycle, int) else state.activation_cycle,
        )
    if kind in ("producer_started", "producer_restarted"):
        session = record.get("producer_session")
        return replace(
            state,
            producer_session=str(session) if session is not None else state.producer_session,
        )
    if kind == "registration_reply":
        rejected = record.get("success") is False or int(record.get("result_code", -1)) == 2
        return replace(state, registration_state="rejected" if rejected else "accepted")
    if kind == "registration_handoff_loaded":
        return replace(
            state,
            registration_state=(
                "accepted" if state.registration_state == "none" else state.registration_state
            ),
        )
    if kind == "fault_detected":
        reason = str(record.get("reason", ""))
        classified = _fault_class(reason)
        updated = replace(state, fault_observed=True, fault_class=classified)
        if "reject" in reason.lower():
            updated = replace(updated, activation_state="rejected")
        return updated
    if kind == "producer_process_exit":
        return replace(state, fault_observed=True, fault_class="process_exit")
    if kind == "motion_phase_entered":
        return replace(state, motion_entered=True)
    if kind == "motion_phase_completed":
        return replace(state, motion_completed=True)
    if kind == "completion":
        return replace(state, completion_observed=True)
    if kind == "successor_requested":
        route = record.get("route")
        return replace(
            state,
            successor_requested_route=str(route) if isinstance(route, str) else None,
        )
    if kind == "successor_observed_active":
        route = record.get("route")
        family = (
            "internal_safe"
            if isinstance(route, str) and route in SAFE_ROUTES
            else state.authority_family
        )
        return replace(
            state,
            successor_installed=True,
            tested_route_active=False,
            authority_family=family,
        )
    if kind == "fallback_triggered":
        route = record.get("route")
        named = isinstance(route, str) and route in SAFE_ROUTES
        return replace(
            state,
            fallback_route=str(route) if named else state.fallback_route,
            fallback_installed=True,
            tested_route_active=False,
            authority_family="internal_safe" if named else state.authority_family,
        )
    if kind in ("cleanup_completed", "requester_completed"):
        return replace(state, terminal=True)
    return state


def _fold_telemetry(
    state: OnlineState, record: Mapping[str, Any], *, external: str, external_nav_state: int | None
) -> OnlineState:
    kind = str(record.get("kind"))
    if kind == "vehicle_status":
        nav_state = record.get("nav_state")
        if not isinstance(nav_state, int) or isinstance(nav_state, bool):
            return state
        if external_nav_state is not None and nav_state == external_nav_state:
            family = external
        elif nav_state in SAFE_NAV_STATES:
            family = "internal_safe"
        else:
            family = "internal_navigator"
        updated = replace(
            state, authority_family=family, tested_route_active=family == external
        )
        if (
            family == "internal_safe"
            and state.tested_route_active
            and state.successor_requested_route is None
        ):
            # The tested route was active, no successor was asked for, and an
            # internal safe route now holds authority.  That is the fallback
            # becoming visible, and telemetry shows it long before a lost
            # producer can report anything about itself.  A handover the
            # producer did request is a release to its successor, not a
            # fallback: measuring both as one made a normal completion look
            # like a producer loss for as long as the episode then ran.
            updated = replace(updated, fallback_installed=True)
        return updated
    if kind == "vehicle_land_detected":
        landed = record.get("landed")
        if landed is False:
            return replace(state, airborne=True)
        if landed is True and state.airborne:
            return replace(state, terminal=True)
        return state
    return state


def derive_online_trajectory(
    records: Sequence[Mapping[str, Any]],
    *,
    mechanism: str,
    external_nav_state: int | None = None,
) -> list[OnlineStep]:
    """Fold merged in-flight records into the states the executor would see.

    `external_nav_state` is the navigation state the tested route presents.
    For the offboard mechanism it is fixed; for the dynamic mechanism it is the
    mode identifier PX4 assigned at registration, which the producer records in
    its own sidecar and which is therefore learned during the fold.
    """

    external = _external_family(mechanism)
    if external_nav_state is None and mechanism == "legacy_offboard":
        external_nav_state = OFFBOARD_NAV_STATE
    state = OnlineState()
    steps: list[OnlineStep] = []
    for record in records:
        kind = str(record.get("kind"))
        if kind in ("registration_reply", "registration_handoff_loaded"):
            mode_id = record.get("mode_id")
            if isinstance(mode_id, int) and not isinstance(mode_id, bool) and mode_id >= 0:
                external_nav_state = mode_id
        if kind in ("vehicle_status", "vehicle_land_detected"):
            state = _fold_telemetry(
                state, record, external=external, external_nav_state=external_nav_state
            )
        else:
            state = _fold_lifecycle(state, record, external=external)
        steps.append(
            OnlineStep(
                monotonic_ns=int(record["received_monotonic_ns"]),
                kind=kind,
                state=state,
            )
        )
    return steps


def state_at(steps: Sequence[OnlineStep], monotonic_ns: int) -> OnlineState:
    """The online state as of a moment, or the initial state before any record."""

    selected = OnlineState()
    for step in steps:
        if step.monotonic_ns > monotonic_ns:
            break
        selected = step.state
    return selected


def validate_vocabularies() -> None:
    """Refuse a projection whose vocabularies drifted from the offline model."""

    if set(FAULT_CLASSES) != {"none", "setpoint_stall", "health_loss", "process_exit", "other"}:
        raise OnlineStateError("online fault classes drifted from the offline model")
    for family in AUTHORITY_FAMILIES:
        if family in ("unknown", "internal_navigator", "internal_safe"):
            continue
        if family not in EXTERNAL_FAMILIES:
            raise OnlineStateError(f"unsupported online authority family: {family}")
    for route in SAFE_ROUTES:
        try:
            if route_family(route) != "internal_safe":
                raise OnlineStateError(f"{route} is not an internal safe route")
        except SemanticStateError as exc:  # pragma: no cover - guarded by the model
            raise OnlineStateError(str(exc)) from exc
