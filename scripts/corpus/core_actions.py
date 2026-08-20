#!/usr/bin/env python3
"""The proposed core action set, as predicates over the semantic state.

Stage 2 selects a minimal representative corpus; this module writes that
selection down in an executable form so it can be checked instead of asserted.
Each core action carries:

* a precondition over the derived semantic state, which is what a closed-loop
  generator would evaluate before choosing the action;
* a marker that recognises the action in retained evidence, so the precondition
  can be replayed against flights that already happened; and
* the cleanup obligation and the contract boundary the action aims at.

Nothing here freezes the corpus.  The selection is signed only after every
action is runtime-selectable and separately qualified.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from scripts.state.online_state import OnlineState
from scripts.state.semantic_state import EXTERNAL_FAMILIES, SemanticState, route_family


class CoreActionError(ValueError):
    """A core action declaration is inconsistent with the model."""


MECHANISMS = ("legacy_offboard", "dynamic_external_mode")
AVAILABILITY = ("implemented", "port_required", "not_applicable", "new")
# How an action reaches the aircraft.  A runtime action is requested during the
# flight and therefore has a moment to choose; a launch configuration is in
# effect from the start, because it must precede the very request it changes the
# outcome of.  Forcing a launch configuration into timing bins would invent a
# choice the generator does not have.
APPLICATIONS = ("runtime", "launch")
# Markers the in-flight executor can observe today.  An action wired to a live
# backend may only require markers from this set, so its precondition is
# checkable before the action is applied rather than after the fact.
OBSERVABLE_LIVE_MARKERS = (
    "route_active",
    "motion_entered",
    "successor_installed",
    "fallback_installed",
)

Precondition = Callable[[SemanticState], bool]
# The in-flight half of a precondition.  The executor cannot fold a closed
# trace while the aircraft is flying, so it evaluates this weakening of the
# offline precondition over the online projection instead.  A weakening can
# hold where the precondition does not; `scripts/corpus/online_state_check.py`
# measures where and for how long rather than assuming it never does.
OnlineGate = Callable[[OnlineState], bool]
Marker = Callable[[Mapping[str, Any], SemanticState, SemanticState], bool]


@dataclass(frozen=True)
class LiveActionProfile:
    """How a wired action is applied and what contract it then owes.

    The workload applies the fault mode it was launched with, so selecting an
    action must select the launch parameters and the plan obligations too.
    Otherwise the policy would name one action while the flight performed
    another.
    """

    fault_mode: str
    completion_expected: bool
    fault_expected: bool
    fallback_expected: bool
    workload_phases: tuple[str, ...]
    # How many times the tested route must be entered for this action to be
    # meaningful.  Re-entry needs two entries in one episode.
    repeat_count: int = 1
    # How many times the tested route is entered across the whole episode. A
    # reclaim enters it twice even though each producer session enters once, so
    # this is separate from the repeat count a single producer performs.
    activation_count: int = 1
    # Whether the plan must preregister an explicit registration rejection.
    registration_rejection_expected: bool = False
    activation_rejection_expected: bool = False
    target_activation_expected: bool = True
    application: str = "runtime"
    # A rejection episode never activates the tested route, so it never moves.
    # Its workload, injection phase and physical obligations differ from the
    # moving profile the other actions share.
    workload_profile: str = "straight_line"
    injection_phase: str = "straight_translation"
    motion_required: bool = True
    # Each action's five timing bins span its own feasible window.  The count
    # stays fixed so systematic enumeration remains well defined; only the
    # seconds differ, because a reclaim has to land inside a ten second window
    # while a stall has the whole active period.
    timing_offsets_ns: tuple[int, ...] = (
        3_500_000_000,
        4_250_000_000,
        5_000_000_000,
        5_750_000_000,
        6_500_000_000,
    )
    # Actions do not share one clock.  A stall is interesting relative to route
    # activation, a re-entry relative to the successor taking over, an adjacent
    # request relative to completion.  Anchoring every action to activation
    # would quietly remove the distinction each one exists to test.
    timing_anchor: str = "route_active"


@dataclass(frozen=True)
class CoreAction:
    """One action proposed for the core corpus."""

    action_id: str
    inventory_action_id: str
    summary: str
    lifecycle_phase: str
    availability: dict[str, str]
    precondition: Precondition
    precondition_text: str
    marker: Marker
    marker_text: str
    cleanup_text: str
    target_boundaries: tuple[str, ...]
    live_markers: tuple[str, ...]
    online_gate: OnlineGate | None = None
    online_gate_text: str = ""
    backend: str | None = None
    live_profile: LiveActionProfile | None = None
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "inventory_action_id": self.inventory_action_id,
            "summary": self.summary,
            "lifecycle_phase": self.lifecycle_phase,
            "availability": dict(sorted(self.availability.items())),
            "precondition": self.precondition_text,
            "marker": self.marker_text,
            "cleanup": self.cleanup_text,
            "target_boundaries": list(self.target_boundaries),
            "live_markers": list(self.live_markers),
            "online_gate": self.online_gate_text or None,
            "backend": self.backend,
            "live_profile": (
                {
                    "fault_mode": self.live_profile.fault_mode,
                    "completion_expected": self.live_profile.completion_expected,
                    "fault_expected": self.live_profile.fault_expected,
                    "fallback_expected": self.live_profile.fallback_expected,
                    "workload_phases": list(self.live_profile.workload_phases),
                    "repeat_count": self.live_profile.repeat_count,
                    "activation_count": self.live_profile.activation_count,
                    "registration_rejection_expected": (
                        self.live_profile.registration_rejection_expected
                    ),
                    "activation_rejection_expected": (
                        self.live_profile.activation_rejection_expected
                    ),
                    "target_activation_expected": (
                        self.live_profile.target_activation_expected
                    ),
                    "application": self.live_profile.application,
                    "workload_profile": self.live_profile.workload_profile,
                    "injection_phase": self.live_profile.injection_phase,
                    "motion_required": self.live_profile.motion_required,
                    "timing_anchor": self.live_profile.timing_anchor,
                    "timing_offsets_ns": list(self.live_profile.timing_offsets_ns),
                }
                if self.live_profile is not None
                else None
            ),
            "notes": self.notes,
        }


def _external_authority(state: SemanticState) -> bool:
    return (
        state.route_family in EXTERNAL_FAMILIES
        and state.lineage == "complete"
        and state.phase != "terminal"
    )


def _any_authority(state: SemanticState) -> bool:
    return (
        state.route is not None
        and state.lineage == "complete"
        and state.phase != "terminal"
    )


def _internal_authority(state: SemanticState) -> bool:
    """Any internal route holding complete authority.

    After a producer loss the vehicle may sit under the internal navigator
    rather than a named safe route.  That distinction does not bear on whether
    reclaiming is legal.
    """

    return (
        state.route_family in ("internal_safe", "internal_navigator")
        and state.lineage == "complete"
        and state.phase != "terminal"
    )


def _internal_safe_authority(state: SemanticState) -> bool:
    return (
        state.route_family == "internal_safe"
        and state.lineage == "complete"
        and state.phase != "terminal"
    )


CORE_ACTIONS: tuple[CoreAction, ...] = (
    CoreAction(
        action_id="stop_owned_setpoint_stream",
        inventory_action_id="owned_setpoint_stall_healthy",
        summary="Stop the owned setpoint stream while proof-of-life continues.",
        lifecycle_phase="execution",
        availability={
            "legacy_offboard": "implemented",
            "dynamic_external_mode": "implemented",
        },
        precondition=lambda state: _external_authority(state)
        and not state.fault_observed,
        precondition_text=(
            "an external route holds complete authority and no fault has been "
            "observed yet in this episode"
        ),
        marker=lambda event, previous, state: str(event.get("kind")) == "fault_detected"
        and "stall" in str(event.get("reason", "")).lower(),
        marker_text="a fault_detected event whose reason names a stalled stream",
        cleanup_text="release to the preregistered successor and land",
        target_boundaries=("command_stale",),
        live_markers=("route_active", "motion_entered"),
        online_gate=lambda state: state.external_authority and not state.fault_observed,
        online_gate_text=(
            "an external route is observed holding authority and no fault has "
            "been observed yet; the command lineage is not observable in flight"
        ),
        backend="owned_setpoint_stall_v1",
        live_profile=LiveActionProfile(
            fault_mode="setpoint_stall",
            completion_expected=True,
            fault_expected=True,
            fallback_expected=False,
            workload_phases=(
                "public_takeoff",
                "stable_hover",
                "route_activation",
                "straight_translation",
                "successor_land",
            ),
        ),
    ),
    CoreAction(
        action_id="terminate_owning_producer",
        inventory_action_id="owned_process_exit_fallback",
        summary="Terminate the producer that owns the installed external route.",
        lifecycle_phase="fallback",
        availability={
            "legacy_offboard": "implemented",
            "dynamic_external_mode": "implemented",
        },
        precondition=lambda state: _external_authority(state)
        and not state.fault_observed,
        precondition_text=(
            "an external route holds complete authority and no fault has been "
            "observed yet in this episode"
        ),
        marker=lambda event, previous, state: str(event.get("kind")) == "fault_detected"
        and (
            "exit" in str(event.get("reason", "")).lower()
            or "process" in str(event.get("reason", "")).lower()
        ),
        marker_text="a fault_detected event whose reason names a producer exit",
        cleanup_text="a complete internal safe route must install without operator action",
        target_boundaries=("fallback_installed",),
        live_markers=("route_active", "motion_entered"),
        online_gate=lambda state: state.external_authority and not state.fault_observed,
        online_gate_text=(
            "an external route is observed holding authority and no fault has "
            "been observed yet; the command lineage is not observable in flight"
        ),
        backend="owned_process_exit_fallback_v1",
        live_profile=LiveActionProfile(
            fault_mode="process_exit",
            completion_expected=False,
            fault_expected=True,
            fallback_expected=True,
            workload_phases=(
                "public_takeoff",
                "stable_hover",
                "route_activation",
                "straight_translation",
                "safe_fallback",
                "successor_land",
            ),
        ),
    ),
    CoreAction(
        action_id="adjacent_land_request",
        inventory_action_id="adjacent_land_request_near_completion",
        summary="Issue a public Land request next to the completion boundary.",
        lifecycle_phase="replacement",
        availability={
            "legacy_offboard": "implemented",
            "dynamic_external_mode": "implemented",
        },
        precondition=_any_authority,
        precondition_text="some route currently holds complete authority",
        marker=lambda event, previous, state: str(event.get("kind")) == "adjacent_request",
        cleanup_text="exactly one successor must win and install completely",
        marker_text="an adjacent_request event",
        target_boundaries=("successor_installed",),
        live_markers=("route_active", "motion_entered"),
        online_gate=lambda state: state.holds_authority and state.airborne,
        online_gate_text=(
            "the vehicle is airborne and some route is observed holding "
            "authority; the command lineage is not observable in flight"
        ),
        backend="owned_adjacent_land_v1",
        live_profile=LiveActionProfile(
            fault_mode="normal",
            # A request placed before the completion legally preempts it, so
            # requiring a completion would be the same self-contradictory
            # obligation that made a Stage A1 cell unreachable.
            completion_expected=False,
            fault_expected=False,
            fallback_expected=False,
            workload_phases=(
                "public_takeoff",
                "stable_hover",
                "route_activation",
                "straight_translation",
                "adjacent_request",
                "successor_land",
            ),
            timing_anchor="route_active",
            # Both producers measure their active period from route activation,
            # so these bins straddle the scheduled completion: two before, one
            # on it, two after. Anchoring on the completion event itself could
            # never place a request before it, and anchoring on motion entry
            # was measured to land every bin about three seconds late because
            # entry is progress-based rather than time-based.
            timing_offsets_ns=(
                7_500_000_000,
                7_750_000_000,
                8_000_000_000,
                8_250_000_000,
                8_500_000_000,
            ),
        ),
        notes=(
            "the request is a public Land command, so porting it from the mode "
            "executor was an anchoring change rather than a new stimulus"
        ),
    ),
    CoreAction(
        action_id="re_enter_route_after_successor",
        inventory_action_id="route_re_entry_through_hold",
        summary="Request the tested route again while an internal safe route holds authority.",
        lifecycle_phase="re_entry",
        availability={
            "legacy_offboard": "implemented",
            "dynamic_external_mode": "implemented",
        },
        precondition=lambda state: _internal_safe_authority(state)
        and state.completion_observed,
        precondition_text=(
            "a completion has been observed and an internal safe route now holds "
            "complete authority"
        ),
        marker=lambda event, previous, state: str(event.get("kind")) == "transition_requested"
        and int(event.get("cycle") or 0) >= 1,
        marker_text="a transition_requested event the producer recorded as a repeat cycle",
        cleanup_text="the final entry must release to a landing successor",
        target_boundaries=("target_installed", "source_revoked"),
        live_markers=("successor_installed",),
        online_gate=lambda state: state.internal_safe_authority
        and state.completion_observed,
        online_gate_text=(
            "a completion has been observed and an internal safe route is "
            "observed holding authority; the command lineage is not observable "
            "in flight"
        ),
        backend="owned_route_re_entry_v1",
        live_profile=LiveActionProfile(
            fault_mode="normal",
            completion_expected=True,
            fault_expected=False,
            fallback_expected=False,
            workload_phases=(
                "public_takeoff",
                "stable_hover",
                "route_activation",
                "straight_translation",
                "successor_hold",
                "route_re_entry",
                "successor_land",
            ),
            repeat_count=2,
            timing_anchor="successor_installed",
        ),
        notes=(
            "the intermediate safe route is a parameter: the core corpus selects "
            "Hold, while the retained evidence that validates this predicate uses "
            "the RTL variant. The derived re_entry phase is deliberately broader "
            "than this action, because a fixture can enter a route twice without "
            "any tester action; the marker therefore uses the producer's own "
            "recorded cycle rather than the system's observed behaviour. The "
            "dynamic requester has no re-entry loop yet"
        ),
    ),
    CoreAction(
        action_id="withhold_health_reply",
        inventory_action_id="activation_rejection_after_health_loss",
        summary="Withhold the external mode health reply so activation is refused.",
        lifecycle_phase="activation",
        availability={
            "legacy_offboard": "not_applicable",
            "dynamic_external_mode": "implemented",
        },
        precondition=lambda state: state.activation_state == "requested"
        and state.route_family not in EXTERNAL_FAMILIES
        and state.phase != "terminal",
        precondition_text=(
            "activation of the external route has been requested and no external "
            "route holds authority yet"
        ),
        marker=lambda event, previous, state: str(event.get("kind")) == "fault_detected"
        and "reject" in str(event.get("reason", "")).lower(),
        marker_text="a fault_detected event whose reason names a rejection",
        cleanup_text="the vehicle must reach an internal safe route and disarm",
        target_boundaries=("activation_rejected",),
        live_markers=(),
        backend="owned_health_withhold_v1",
        live_profile=LiveActionProfile(
            fault_mode="normal",
            completion_expected=False,
            fault_expected=True,
            fallback_expected=False,
            activation_rejection_expected=True,
            target_activation_expected=False,
            activation_count=0,
            workload_phases=(
                "public_takeoff",
                "stable_hover",
                "activation_rejected",
                "successor_land",
            ),
            timing_offsets_ns=(),
            application="launch",
            workload_profile="hover",
            injection_phase="stable_hover",
            motion_required=False,
        ),
        notes=(
            "legacy offboard has no health-reply protocol, so this is not "
            "portable. It is a launch configuration rather than a runtime "
            "action: the withhold must already be in effect when the activation "
            "is requested, so there is no moment to choose and no request to "
            "record. The policy still selects whether an episode tests the "
            "rejection path"
        ),
    ),
    CoreAction(
        action_id="exhaust_registration_capacity",
        inventory_action_id="registration_capacity_rejection",
        summary="Register components until a further registration is refused.",
        lifecycle_phase="registration",
        availability={
            "legacy_offboard": "not_applicable",
            "dynamic_external_mode": "implemented",
        },
        precondition=_any_authority,
        precondition_text="the episode is running and some route holds complete authority",
        marker=lambda event, previous, state: str(event.get("kind")) == "registration"
        and int(event.get("result_code", -1)) == 2,
        marker_text="a registration event whose result code reports a rejection",
        cleanup_text="stop every additional component and keep the primary session consistent",
        target_boundaries=("registration_rejected",),
        live_markers=("route_active",),
        online_gate=lambda state: state.holds_authority and state.airborne,
        online_gate_text=(
            "the vehicle is airborne and some route is observed holding "
            "authority; the command lineage is not observable in flight"
        ),
        backend="owned_registration_capacity_v1",
        live_profile=LiveActionProfile(
            fault_mode="normal",
            completion_expected=True,
            fault_expected=False,
            fallback_expected=False,
            registration_rejection_expected=True,
            workload_phases=(
                "public_takeoff",
                "stable_hover",
                "route_activation",
                "straight_translation",
                "registration_capacity",
                "successor_land",
            ),
            timing_anchor="route_active",
            timing_offsets_ns=(
                1_000_000_000,
                1_500_000_000,
                2_000_000_000,
                2_500_000_000,
                3_000_000_000,
            ),
        ),
        notes=(
            "legacy offboard has no registration protocol, so this is not "
            "portable. Starting all eight components on the policy's request "
            "was flown twice and failed both times the same way: the boundary "
            "was reached, with two refused, but registering them spanned the "
            "whole active period and the moving profile never reached its "
            "completion progress. The seven legal slots are now filled during "
            "setup and the policy times only the eighth, which is the one that "
            "must be refused and the one the action is actually about"
        ),
    ),
    CoreAction(
        action_id="restart_producer_after_loss",
        inventory_action_id="producer_restart_after_exit",
        summary="Restart the producer after a loss and reclaim authority.",
        lifecycle_phase="fallback",
        availability={
            "legacy_offboard": "implemented",
            "dynamic_external_mode": "implemented",
        },
        precondition=lambda state: state.fault_class == "process_exit"
        and _internal_authority(state),
        precondition_text=(
            "a producer loss has been observed and an internal route now holds "
            "complete authority"
        ),
        marker=lambda event, previous, state: str(event.get("kind")) == "transition_requested"
        and route_family(event.get("target_route")) in EXTERNAL_FAMILIES
        and previous.fault_class == "process_exit",
        marker_text=(
            "a transition_requested returning to an external route after a "
            "producer loss"
        ),
        cleanup_text="either the reclaim installs completely or the safe route is retained",
        target_boundaries=("target_installed",),
        live_markers=("fallback_installed",),
        # The offline precondition asks for a classified producer loss.  In
        # flight the loss is not classifiable in time: a lost producer stops
        # writing, and the runner learns it by polling, about eleven seconds
        # after telemetry already shows the safe route.  The gate therefore
        # asks for the effect the loss produced, which telemetry does show.
        online_gate=lambda state: state.fallback_installed
        and state.internal_authority,
        online_gate_text=(
            "a safe route is observed to have taken over from the tested route "
            "and an internal route holds authority; the loss that caused it is "
            "not classifiable in flight"
        ),
        backend="owned_producer_restart_v1",
        live_profile=LiveActionProfile(
            fault_mode="process_exit",
            completion_expected=True,
            fault_expected=True,
            # The reclaim preempts the safe route by design, so requiring a
            # completely installed fallback would be a self-contradictory
            # obligation rather than a contract the system could satisfy.
            fallback_expected=False,
            workload_phases=(
                "public_takeoff",
                "stable_hover",
                "route_activation",
                "straight_translation",
                "safe_fallback",
                "route_reclaim",
                "successor_land",
            ),
            repeat_count=1,
            activation_count=2,
            timing_anchor="fallback_installed",
            # Measured: ten seconds from the telemetry-visible fallback to
            # disarm, and the reclaim spends about three of them starting its
            # process and prestreaming before it can request.
            timing_offsets_ns=(
                500_000_000,
                1_000_000_000,
                1_500_000_000,
                2_000_000_000,
                2_500_000_000,
            ),
        ),
        notes=(
            "the only proposed action whose legality depends on the outcome of an "
            "earlier action, which is what separates feedback-guided generation "
            "from feedback-free generation. A first attempt found it unreachable "
            "because the runner learned of the producer loss by polling the "
            "process, about eleven seconds after telemetry already showed the "
            "installed safe route, by which time the aircraft had landed. The "
            "loss is now observed from telemetry, which leaves the measured ten "
            "second window; the tested failsafe configuration is unchanged"
        ),
    ),
)


def validate_declarations() -> None:
    """Refuse a declaration that cannot be executed or read back."""

    identifiers: set[str] = set()
    for action in CORE_ACTIONS:
        if action.action_id in identifiers:
            raise CoreActionError(f"duplicate core action: {action.action_id}")
        identifiers.add(action.action_id)
        if set(action.availability) != set(MECHANISMS):
            raise CoreActionError(
                f"{action.action_id}: availability must cover exactly the compared mechanisms"
            )
        for mechanism, status in action.availability.items():
            if status not in AVAILABILITY:
                raise CoreActionError(
                    f"{action.action_id}: unsupported availability {status} for {mechanism}"
                )
        if not action.target_boundaries:
            raise CoreActionError(f"{action.action_id}: a core action must target a boundary")
        if not action.precondition_text.strip() or not action.marker_text.strip():
            raise CoreActionError(f"{action.action_id}: precondition and marker need text")
        # A precondition must be a real restriction: the initial state of an
        # episode may never satisfy it, or the action would be unconditioned.
        if action.precondition(SemanticState()):
            raise CoreActionError(
                f"{action.action_id}: precondition holds in the empty initial state"
            )
        launch = action.live_profile is not None and action.live_profile.application == "launch"
        # A runtime action is chosen in flight, so it needs a gate the flight
        # can evaluate, and that gate must be a real restriction for the same
        # reason the precondition must be.  A launch configuration is in effect
        # before the episode observes anything, so gating it would invent a
        # decision moment it does not have, which is the mistake that judging
        # every precondition at its decision time already made.
        if action.backend is not None and not launch:
            if action.online_gate is None or not action.online_gate_text.strip():
                raise CoreActionError(
                    f"{action.action_id}: a runtime action needs an online gate and its text"
                )
            if action.online_gate(OnlineState()):
                raise CoreActionError(
                    f"{action.action_id}: online gate holds in the empty initial state"
                )
        elif action.online_gate is not None:
            raise CoreActionError(
                f"{action.action_id}: only a wired runtime action may declare an online gate"
            )
        if launch:
            # A launch configuration is in effect before the flight observes
            # anything, so it waits on nothing.
            if action.live_markers:
                raise CoreActionError(
                    f"{action.action_id}: a launch configuration waits on no marker"
                )
        else:
            if not action.live_markers:
                raise CoreActionError(
                    f"{action.action_id}: a runtime action needs a live marker"
                )
            if action.backend is not None and not set(action.live_markers) <= set(
                OBSERVABLE_LIVE_MARKERS
            ):
                raise CoreActionError(
                    f"{action.action_id}: a wired action may only require observable markers"
                )
        if (action.backend is None) != (action.live_profile is None):
            raise CoreActionError(
                f"{action.action_id}: a wired action needs a live profile and only a wired action may have one"
            )
        if action.live_profile is not None:
            application = action.live_profile.application
            if application not in APPLICATIONS:
                raise CoreActionError(
                    f"{action.action_id}: unsupported application {application}"
                )
            offsets = action.live_profile.timing_offsets_ns
            if sorted(offsets) != list(offsets) or (offsets and offsets[0] < 0):
                raise CoreActionError(
                    f"{action.action_id}: timing offsets must be ordered and non-negative"
                )
            if application == "launch":
                if offsets:
                    raise CoreActionError(
                        f"{action.action_id}: a launch configuration has no timing to choose"
                    )
            else:
                if len(offsets) != 5:
                    raise CoreActionError(
                        f"{action.action_id}: a runtime action needs five timing bins"
                    )
                anchor = action.live_profile.timing_anchor
                if anchor not in action.live_markers:
                    raise CoreActionError(
                        f"{action.action_id}: the timing anchor must be one of its live markers"
                    )
                if anchor not in OBSERVABLE_LIVE_MARKERS:
                    raise CoreActionError(
                        f"{action.action_id}: the timing anchor must be observable in flight"
                    )


def core_action(action_id: str) -> CoreAction:
    for action in CORE_ACTIONS:
        if action.action_id == action_id:
            return action
    raise CoreActionError(f"unknown core action: {action_id}")


def wired_actions(mechanism: str) -> tuple[CoreAction, ...]:
    """Core actions that a live backend can apply for this mechanism today."""

    if mechanism not in MECHANISMS:
        raise CoreActionError(f"unsupported mechanism: {mechanism}")
    return tuple(
        action
        for action in CORE_ACTIONS
        if action.backend is not None
        and action.availability[mechanism] == "implemented"
    )


def live_profile(action_id: str) -> LiveActionProfile:
    """How to launch the flight that applies this action."""

    profile = core_action(action_id).live_profile
    if profile is None:
        raise CoreActionError(f"{action_id} has no live backend to apply it")
    return profile


def core_action_records() -> list[dict[str, Any]]:
    validate_declarations()
    return [action.as_dict() for action in CORE_ACTIONS]
