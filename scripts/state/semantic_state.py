#!/usr/bin/env python3
"""Deterministic semantic state derived from normalized route evidence.

The model is the target generator state defined in `docs/ROUTE_MODEL.md`:
route identity/family/epoch, authority owner and command lineage, lifecycle
phase, health and command freshness, successor and fallback progress, coarse
motion context, and a bounded action history.

Two rules shape this module:

* A declared navigation-mode label is never an input.  The fold consumes only
  Runtime Route Instance identity, lifecycle events and command-subject times.
* Absent evidence is represented as an explicit unknown.  The extractor never
  infers a phase, a lineage stage, or a motion context it did not observe.

The fold is a pure function of the ordered event list, so replaying equivalent
retained evidence yields an identical trajectory digest.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
from typing import Any, Iterable, Mapping, Sequence

from scripts.model.runtime_route import (
    EFFECT_EVENT_KINDS,
    IDENTITY_FIELDS,
    canonical_json,
)


class SemanticStateError(ValueError):
    """Evidence cannot be folded into a deterministic semantic state."""


ROUTE_FAMILIES = {
    "px4_internal": "internal_navigator",
    "internal_hold": "internal_safe",
    "internal_rtl": "internal_safe",
    "internal_land": "internal_safe",
    "internal_recovery": "internal_safe",
    "legacy_offboard": "external_offboard",
    "dynamic_external_mode": "external_dynamic",
    "mode_executor": "external_executor",
}
EXTERNAL_FAMILIES = frozenset(
    {"external_offboard", "external_dynamic", "external_executor"}
)
SAFE_ROUTES = frozenset(
    {"internal_hold", "internal_rtl", "internal_land", "internal_recovery"}
)
LIFECYCLE_PHASES = (
    "idle",
    "registered",
    "activation_requested",
    "activated",
    "executing",
    "completed",
    "replacing",
    "re_entry",
    "fallback",
    "terminal",
)
LINEAGE_STAGES = (
    "command_consumed",
    "controller_output",
    "allocator_output",
    "actuator_write",
)
FRESHNESS_STATES = ("unknown", "fresh", "aging", "stale")
FAULT_CLASSES = ("none", "setpoint_stall", "health_loss", "process_exit", "other")
MOTION_PHASES = (
    "unobserved",
    "ground",
    "takeoff",
    "hover",
    "translating",
    "landing",
)
ACTION_EVENT_KINDS = frozenset(
    {
        "transition_requested",
        "activation_requested",
        "adjacent_request",
        "registration",
        "completion",
        "fault_detected",
    }
)
TIMING_BUCKETS = ("pre_activation", "t0_1s", "t1_3s", "t3_8s", "t8s_plus")
TIMING_BOUNDARIES_NS = (1_000_000_000, 3_000_000_000, 8_000_000_000)
CONTRACT_BOUNDARIES = (
    "source_revoked",
    "target_installed",
    "target_partially_installed",
    "command_stale",
    "successor_requested",
    "successor_installed",
    "fallback_installed",
    "registration_rejected",
    "activation_rejected",
    "evidence_gap",
)
DEFAULT_MAXIMUM_COMMAND_AGE_NS = 200_000_000
DEFAULT_HISTORY_LIMIT = 8


def route_family(route: str | None) -> str:
    if route is None:
        return "none"
    try:
        return ROUTE_FAMILIES[route]
    except KeyError as exc:
        raise SemanticStateError(f"unsupported route: {route}") from exc


def _registration_rejected(event: Mapping[str, Any]) -> bool:
    """Rejection marker used by the Registration Contract Oracle.

    PX4 reports the outcome as a numeric `result_code`; the boolean form only
    appears in synthetic evidence.  Both must mean the same thing here, or the
    derived state would disagree with the Oracle about the same event.
    """

    return int(event.get("result_code", -1)) == 2 or bool(event.get("rejected"))


def _activation_rejection_fault(event: Mapping[str, Any]) -> bool:
    return (
        "reject" in str(event.get("reason", "")).lower()
        or int(event.get("result_code", -1)) == 2
    )


def _fault_class(reason: str) -> str:
    lowered = reason.lower()
    if "stall" in lowered:
        return "setpoint_stall"
    if "health" in lowered:
        return "health_loss"
    if "exit" in lowered or "process" in lowered:
        return "process_exit"
    return "other"


def _epoch_ordinal(index: int) -> str:
    if index <= 0:
        return "e0"
    return f"e{index}" if index < 3 else "e3_plus"


class MotionContext:
    """Coarse mission context sampled from an independent physical source.

    The trace itself carries no physical observation, so motion context is an
    optional input.  Without samples every state reports `unobserved` instead
    of a guessed phase.
    """

    def __init__(self, samples: Iterable[tuple[int, str]] = ()) -> None:
        ordered: list[tuple[int, str]] = []
        for timestamp_ns, phase in samples:
            if not isinstance(timestamp_ns, int) or timestamp_ns < 0:
                raise SemanticStateError("motion sample time must be a non-negative integer")
            if phase not in MOTION_PHASES or phase == "unobserved":
                raise SemanticStateError(f"unsupported motion phase: {phase}")
            if ordered and timestamp_ns < ordered[-1][0]:
                raise SemanticStateError("motion samples must be ordered by time")
            ordered.append((timestamp_ns, phase))
        self._samples = tuple(ordered)

    @property
    def observed(self) -> bool:
        return bool(self._samples)

    def phase_at(self, timestamp_ns: int) -> str:
        selected = "unobserved"
        for sample_ns, phase in self._samples:
            if sample_ns > timestamp_ns:
                break
            selected = phase
        return selected


@dataclass(frozen=True)
class SemanticState:
    """One derived state of the tested authority path."""

    # 1. route identity, family and epoch
    route: str | None = None
    route_family: str = "none"
    route_epoch: str | None = None
    route_epoch_index: int = 0
    # 2. authority owner and command lineage
    lifecycle_owner: str | None = None
    executor_owner: str | None = None
    producer_session: str | None = None
    registration_id: str | None = None
    activation_id: str | None = None
    controller_id: str | None = None
    allocator_id: str | None = None
    writer_id: str | None = None
    lineage_stages: tuple[str, ...] = ()
    # 3. lifecycle phase
    phase: str = "idle"
    pending_target_route: str | None = None
    registration_state: str = "none"
    activation_state: str = "none"
    re_entry_count: int = 0
    # 4. health and command freshness
    freshness: str = "unknown"
    command_age_ns: int | None = None
    fault_class: str = "none"
    fault_observed: bool = False
    # 5. successor and fallback progress
    successor_requested_route: str | None = None
    successor_installed: bool = False
    completion_observed: bool = False
    fallback_route: str | None = None
    fallback_installed: bool = False
    source_revoked: bool = False
    # 6. coarse motion or mission context
    motion_phase: str = "unobserved"
    # 7. bounded action history
    action_history: tuple[str, ...] = ()
    # evidence quality carried alongside the state
    evidence_gap: bool = False

    @property
    def lineage(self) -> str:
        if not self.lineage_stages:
            return "none"
        if len(self.lineage_stages) == len(LINEAGE_STAGES):
            return "complete"
        return "partial"

    @property
    def owner_class(self) -> str:
        if self.lifecycle_owner is None:
            return "none"
        return "external" if self.route_family in EXTERNAL_FAMILIES else "internal"

    def key(self) -> str:
        """Bounded coverage abstraction of this state.

        Identity strings stay in the record; the coverage key keeps only the
        derived, finite classification so state and edge coverage cannot grow
        with run identifiers.
        """

        successor = (
            "installed"
            if self.successor_installed
            else ("requested" if self.successor_requested_route else "none")
        )
        return "|".join(
            (
                f"family={self.route_family}",
                f"epoch={_epoch_ordinal(self.route_epoch_index)}",
                f"owner={self.owner_class}",
                f"phase={self.phase}",
                f"lineage={self.lineage}",
                f"freshness={self.freshness}",
                f"successor={successor}",
                f"fallback={'installed' if self.fallback_installed else ('triggered' if self.fallback_route else 'none')}",
                f"fault={self.fault_class}",
                f"motion={self.motion_phase}",
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "route_identity": {
                "route": self.route,
                "route_family": self.route_family,
                "route_epoch": self.route_epoch,
                "route_epoch_index": self.route_epoch_index,
            },
            "authority": {
                "lifecycle_owner": self.lifecycle_owner,
                "executor_owner": self.executor_owner,
                "producer_session": self.producer_session,
                "registration_id": self.registration_id,
                "activation_id": self.activation_id,
                "controller_id": self.controller_id,
                "allocator_id": self.allocator_id,
                "writer_id": self.writer_id,
                "owner_class": self.owner_class,
                "lineage": self.lineage,
                "lineage_stages": list(self.lineage_stages),
            },
            "lifecycle": {
                "phase": self.phase,
                "completion_observed": self.completion_observed,
                "pending_target_route": self.pending_target_route,
                "registration_state": self.registration_state,
                "activation_state": self.activation_state,
                "re_entry_count": self.re_entry_count,
                "source_revoked": self.source_revoked,
            },
            "freshness": {
                "state": self.freshness,
                "command_age_ns": self.command_age_ns,
                "fault_class": self.fault_class,
                "fault_observed": self.fault_observed,
            },
            "progression": {
                "successor_requested_route": self.successor_requested_route,
                "successor_installed": self.successor_installed,
                "fallback_route": self.fallback_route,
                "fallback_installed": self.fallback_installed,
            },
            "motion": {"phase": self.motion_phase},
            "action_history": list(self.action_history),
            "evidence_gap": self.evidence_gap,
            "state_key": self.key(),
        }


@dataclass(frozen=True)
class SemanticStep:
    """One folded event and the state it produced."""

    sequence: int
    timestamp_ns: int
    kind: str
    state: SemanticState
    action: str | None = None
    timing_bucket: str | None = None

    def as_dict(self) -> dict[str, Any]:
        record = {
            "sequence": self.sequence,
            "timestamp_ns": self.timestamp_ns,
            "kind": self.kind,
            "state": self.state.as_dict(),
        }
        if self.action is not None:
            record["action"] = self.action
            record["timing_bucket"] = self.timing_bucket
        return record


@dataclass
class Coverage:
    """Visited states, semantic edges, phases and contract boundaries."""

    states: dict[str, int] = field(default_factory=dict)
    edges: dict[str, int] = field(default_factory=dict)
    phases: dict[str, int] = field(default_factory=dict)
    actions: dict[str, int] = field(default_factory=dict)
    contract_boundaries: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "distinct_states": len(self.states),
            "distinct_edges": len(self.edges),
            "distinct_phases": len(self.phases),
            "distinct_actions": len(self.actions),
            "distinct_contract_boundaries": len(self.contract_boundaries),
            "states": dict(sorted(self.states.items())),
            "edges": dict(sorted(self.edges.items())),
            "phases": dict(sorted(self.phases.items())),
            "actions": dict(sorted(self.actions.items())),
            "contract_boundaries": dict(sorted(self.contract_boundaries.items())),
        }


@dataclass(frozen=True)
class Trajectory:
    """The ordered states derived from one closed trace."""

    run_id: str
    steps: tuple[SemanticStep, ...]
    coverage: Coverage
    instrumented_events: int
    public_events: int

    @property
    def final_state(self) -> SemanticState:
        return self.steps[-1].state if self.steps else SemanticState()

    def state_keys(self) -> tuple[str, ...]:
        return tuple(step.state.key() for step in self.steps)

    def edges(self) -> tuple[str, ...]:
        return tuple(sorted(self.coverage.edges))

    def digest(self) -> str:
        """Stable digest of the derived trajectory, not of the input file."""

        payload = {
            "run_id": self.run_id,
            "steps": [
                {
                    "sequence": step.sequence,
                    "kind": step.kind,
                    "action": step.action,
                    "timing_bucket": step.timing_bucket,
                    "state_key": step.state.key(),
                }
                for step in self.steps
            ],
        }
        return "sha256:" + hashlib.sha256(canonical_json(payload)).hexdigest()

    def as_summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "steps": len(self.steps),
            "instrumented_events": self.instrumented_events,
            "public_events": self.public_events,
            "trajectory_digest": self.digest(),
            "final_state": self.final_state.as_dict(),
            "coverage": self.coverage.as_dict(),
        }


MODE_LABEL_FIELDS = (
    "nav_state",
    "nav_state_user_intention",
    "mode",
    "declared_mode",
    "flight_mode",
)
# A value no PX4 navigation state can take, used only to prove by replay that
# the fold never reads a declared-mode label.
MODE_LABEL_SENTINEL = -999


def mode_label_fields(events: Iterable[Mapping[str, Any]]) -> list[str]:
    """Declared-mode observation fields actually present in the evidence."""

    observed: set[str] = set()
    for event in events:
        observed.update(name for name in MODE_LABEL_FIELDS if name in event)
    return sorted(observed)


def without_mode_labels(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The same events with every declared-mode observation field removed."""

    return [
        {name: value for name, value in event.items() if name not in MODE_LABEL_FIELDS}
        for event in events
    ]


def with_perturbed_mode_labels(
    events: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """The same events with every declared-mode field replaced by a sentinel."""

    perturbed: list[dict[str, Any]] = []
    for event in events:
        copy = dict(event)
        for name in MODE_LABEL_FIELDS:
            if name in copy:
                copy[name] = MODE_LABEL_SENTINEL
        perturbed.append(copy)
    return perturbed


def is_instrumented(event: Mapping[str, Any]) -> bool:
    """True when the event needs the repository observability instrumentation.

    Normalized events that carry a raw PX4 observation domain are produced by
    the tracked observability patches.  Everything else is available from
    ordinary public interfaces and host-side lifecycle records.
    """

    return "raw_source_domain" in event


def public_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The reduced-observation view used to measure instrumentation dependence."""

    return [dict(event) for event in events if not is_instrumented(event)]


def _timing_bucket(timestamp_ns: int, activation_ns: int | None) -> str:
    """Bucket an action time relative to the current route activation."""

    if activation_ns is None:
        return TIMING_BUCKETS[0]
    elapsed = timestamp_ns - activation_ns
    for boundary, name in zip(TIMING_BOUNDARIES_NS, TIMING_BUCKETS[1:]):
        if elapsed < boundary:
            return name
    return TIMING_BUCKETS[-1]


def _action_label(event: Mapping[str, Any], state: SemanticState) -> str:
    kind = str(event["kind"])
    if kind == "transition_requested":
        target = event.get("target_route")
        if target in SAFE_ROUTES and state.route_family in EXTERNAL_FAMILIES:
            return "release_to_successor"
        if route_family(target) in EXTERNAL_FAMILIES:
            return "request_external_route"
        return "request_internal_route"
    if kind == "registration":
        return "register_rejected" if _registration_rejected(event) else "register"
    if kind == "activation_requested":
        return "request_activation"
    if kind == "adjacent_request":
        return "adjacent_request"
    if kind == "completion":
        return "complete"
    return "fault_" + _fault_class(str(event.get("reason", "")))


def _identity_fields(event: Mapping[str, Any]) -> dict[str, str] | None:
    if any(not event.get(name) for name in IDENTITY_FIELDS):
        return None
    return {name: str(event[name]) for name in IDENTITY_FIELDS}


def _ordered(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Consume the canonical collection order fixed by the trace hash chain.

    The chain, not the wall clock, defines the order of a closed trace, so the
    fold requires a strictly increasing sequence and never re-sorts by time.
    Timestamps remain the input to freshness and timing buckets only.
    """

    ordered: list[dict[str, Any]] = []
    previous: int | None = None
    for event in events:
        for required in ("kind", "sequence", "timestamp_ns", "run_id"):
            if required not in event:
                raise SemanticStateError(f"event is missing {required}")
        sequence = int(event["sequence"])
        timestamp_ns = int(event["timestamp_ns"])
        if sequence < 0 or timestamp_ns < 0:
            raise SemanticStateError("sequence and timestamp_ns must be non-negative")
        if previous is not None and sequence <= previous:
            raise SemanticStateError(
                f"events must be strictly ordered by sequence; {sequence} follows {previous}"
            )
        previous = sequence
        ordered.append(dict(event))
    return ordered


class _Fold:
    """Mutable fold bookkeeping kept out of the frozen state record."""

    def __init__(self, maximum_command_age_ns: int, history_limit: int) -> None:
        self.maximum_command_age_ns = maximum_command_age_ns
        self.history_limit = history_limit
        self.activation_ns: int | None = None
        self.route_epochs: dict[str, list[str]] = {}
        self.activated_routes: list[str] = []
        self.coverage = Coverage()
        self.instrumented = 0
        self.public = 0

    def epoch_index(self, route: str, epoch: str) -> int:
        seen = self.route_epochs.setdefault(route, [])
        if epoch not in seen:
            seen.append(epoch)
        return seen.index(epoch) + 1

    def record_boundary(self, name: str) -> None:
        if name not in CONTRACT_BOUNDARIES:
            raise SemanticStateError(f"unsupported contract boundary: {name}")
        self.coverage.contract_boundaries[name] = (
            self.coverage.contract_boundaries.get(name, 0) + 1
        )


def _apply(event: Mapping[str, Any], state: SemanticState, fold: _Fold) -> SemanticState:
    kind = str(event["kind"])
    timestamp_ns = int(event["timestamp_ns"])
    identity = _identity_fields(event)

    if kind == "collector_gap":
        fold.record_boundary("evidence_gap")
        return replace(state, evidence_gap=True, freshness="unknown", command_age_ns=None)

    if kind == "registration":
        if _registration_rejected(event):
            fold.record_boundary("registration_rejected")
            return replace(state, registration_state="rejected")
        updated = replace(
            state,
            registration_state="registered",
            registration_id=(identity or {}).get("registration_id", state.registration_id),
        )
        if updated.phase in {"idle", "activation_requested"}:
            updated = replace(updated, phase="registered")
        return updated

    if kind == "transition_requested":
        target = event.get("target_route")
        if target is not None and target not in ROUTE_FAMILIES:
            raise SemanticStateError(f"unsupported target_route: {target}")
        updated = replace(state, pending_target_route=target)
        if target in SAFE_ROUTES and state.route_family in EXTERNAL_FAMILIES:
            fold.record_boundary("successor_requested")
            updated = replace(
                updated, phase="replacing", successor_requested_route=target
            )
        elif target in fold.activated_routes:
            updated = replace(updated, phase="re_entry", re_entry_count=state.re_entry_count + 1)
        else:
            updated = replace(updated, phase="activation_requested")
        return updated

    if kind == "activation_requested":
        return replace(state, activation_state="requested", phase="activation_requested")

    if kind == "activation":
        if identity is None:
            raise SemanticStateError("activation event has incomplete route identity")
        route = identity["route"]
        epoch_index = fold.epoch_index(route, identity["route_epoch"])
        if route not in fold.activated_routes:
            fold.activated_routes.append(route)
        fold.activation_ns = timestamp_ns
        return replace(
            state,
            route=route,
            route_family=route_family(route),
            route_epoch=identity["route_epoch"],
            route_epoch_index=epoch_index,
            lifecycle_owner=identity["lifecycle_owner"],
            executor_owner=identity["executor_owner"],
            producer_session=identity["producer_session"],
            registration_id=identity["registration_id"],
            activation_id=identity["activation_id"],
            controller_id=identity["controller_id"],
            allocator_id=identity["allocator_id"],
            writer_id=identity["writer_id"],
            lineage_stages=(),
            phase="activated",
            activation_state="activated",
            pending_target_route=None,
            # A fault is an episode-level observation.  Installing the next
            # route does not erase that this episode already saw one.
            freshness="unknown",
            command_age_ns=None,
        )

    if kind in EFFECT_EVENT_KINDS:
        if identity is None or identity["route"] != state.route:
            return state
        if identity["activation_id"] != state.activation_id:
            return state
        stages = state.lineage_stages
        if kind in LINEAGE_STAGES and kind not in stages:
            stages = tuple(
                name for name in LINEAGE_STAGES if name in set(stages) | {kind}
            )
        updated = replace(state, lineage_stages=stages)
        if kind == "command_consumed":
            subject = event.get("command_subject_ns")
            if isinstance(subject, int):
                age = timestamp_ns - subject
                if age < 0:
                    raise SemanticStateError(
                        "command_subject_ns is later than its consumption time"
                    )
                bound = fold.maximum_command_age_ns
                if age > bound:
                    freshness = "stale"
                    fold.record_boundary("command_stale")
                elif age * 2 > bound:
                    freshness = "aging"
                else:
                    freshness = "fresh"
                updated = replace(updated, command_age_ns=age, freshness=freshness)
        if len(updated.lineage_stages) == len(LINEAGE_STAGES):
            if state.lineage != "complete":
                fold.record_boundary("target_installed")
                if updated.route == state.successor_requested_route:
                    updated = replace(updated, successor_installed=True)
                    fold.record_boundary("successor_installed")
                elif state.completion_observed and updated.route in SAFE_ROUTES:
                    # A completed external route whose authority is taken over
                    # by a fully installed internal safe route progressed to
                    # that successor even when no separate request was traced.
                    updated = replace(
                        updated,
                        successor_requested_route=updated.route,
                        successor_installed=True,
                    )
                    fold.record_boundary("successor_installed")
                if updated.route == state.fallback_route:
                    updated = replace(updated, fallback_installed=True)
                    fold.record_boundary("fallback_installed")
            if updated.phase in {"activated", "re_entry"}:
                updated = replace(updated, phase="executing")
        elif state.lineage == "none":
            fold.record_boundary("target_partially_installed")
        return updated

    if kind == "revocation":
        if identity is None:
            raise SemanticStateError("revocation event has incomplete route identity")
        if identity["route"] != state.route or identity["activation_id"] != state.activation_id:
            return state
        fold.record_boundary("source_revoked")
        fold.activation_ns = None
        return replace(
            state,
            route=None,
            route_family="none",
            route_epoch=None,
            route_epoch_index=0,
            lifecycle_owner=None,
            executor_owner=None,
            producer_session=None,
            activation_id=None,
            controller_id=None,
            allocator_id=None,
            writer_id=None,
            lineage_stages=(),
            activation_state="revoked",
            source_revoked=True,
            freshness="unknown",
            command_age_ns=None,
            phase="replacing" if state.pending_target_route else "idle",
        )

    if kind == "owner_changed":
        if identity is None or identity["route"] != state.route:
            return state
        return replace(
            state,
            lifecycle_owner=identity["lifecycle_owner"],
            executor_owner=identity["executor_owner"],
        )

    if kind == "completion":
        if event.get("route") not in (None, state.route) and state.route is not None:
            return state
        return replace(state, phase="completed", completion_observed=True)

    if kind == "fault_detected":
        updated = replace(
            state,
            fault_class=_fault_class(str(event.get("reason", ""))),
            fault_observed=True,
        )
        if _activation_rejection_fault(event):
            fold.record_boundary("activation_rejected")
            updated = replace(updated, activation_state="rejected")
        return updated

    if kind == "fallback_triggered":
        route = event.get("route")
        if route is not None and route not in ROUTE_FAMILIES:
            raise SemanticStateError(f"unsupported fallback route: {route}")
        return replace(state, phase="fallback", fallback_route=route)

    if kind == "terminal_state":
        return replace(state, phase="terminal")

    if kind == "cleanup_completed":
        return replace(state, phase="terminal")

    return state


def derive_trajectory(
    events: Sequence[Mapping[str, Any]],
    *,
    maximum_command_age_ns: int = DEFAULT_MAXIMUM_COMMAND_AGE_NS,
    motion: MotionContext | None = None,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
) -> Trajectory:
    """Fold one ordered closed trace into its semantic-state trajectory."""

    if maximum_command_age_ns <= 0:
        raise SemanticStateError("maximum_command_age_ns must be positive")
    if history_limit <= 0:
        raise SemanticStateError("history_limit must be positive")
    ordered = _ordered(events)
    if not ordered:
        raise SemanticStateError("a trajectory requires at least one event")
    run_ids = {str(event["run_id"]) for event in ordered}
    if len(run_ids) != 1:
        raise SemanticStateError("a trajectory requires exactly one run identity")
    motion = motion or MotionContext()
    fold = _Fold(maximum_command_age_ns, history_limit)

    state = SemanticState()
    steps: list[SemanticStep] = []
    for event in ordered:
        if is_instrumented(event):
            fold.instrumented += 1
        else:
            fold.public += 1
        kind = str(event["kind"])
        timestamp_ns = int(event["timestamp_ns"])
        previous_key = state.key()
        action: str | None = None
        bucket: str | None = None
        if kind in ACTION_EVENT_KINDS:
            action = _action_label(event, state)
            bucket = _timing_bucket(timestamp_ns, fold.activation_ns)
            fold.coverage.actions[action] = fold.coverage.actions.get(action, 0) + 1
        state = _apply(event, state, fold)
        state = replace(state, motion_phase=motion.phase_at(timestamp_ns))
        if action is not None:
            history = (*state.action_history, action)[-history_limit:]
            state = replace(state, action_history=history)
            edge = f"{previous_key} -[{action}@{bucket}]-> {state.key()}"
            fold.coverage.edges[edge] = fold.coverage.edges.get(edge, 0) + 1
        key = state.key()
        fold.coverage.states[key] = fold.coverage.states.get(key, 0) + 1
        fold.coverage.phases[state.phase] = fold.coverage.phases.get(state.phase, 0) + 1
        steps.append(
            SemanticStep(
                sequence=int(event["sequence"]),
                timestamp_ns=timestamp_ns,
                kind=kind,
                state=state,
                action=action,
                timing_bucket=bucket,
            )
        )
    return Trajectory(
        run_id=run_ids.pop(),
        steps=tuple(steps),
        coverage=fold.coverage,
        instrumented_events=fold.instrumented,
        public_events=fold.public,
    )


def maximum_command_age_from_plan(plan: Mapping[str, Any] | None) -> int:
    """Read the frozen freshness bound without inventing a default silently."""

    if plan is None:
        return DEFAULT_MAXIMUM_COMMAND_AGE_NS
    thresholds = plan.get("thresholds")
    if not isinstance(thresholds, dict):
        raise SemanticStateError("plan thresholds must be an object")
    value = thresholds.get("maximum_command_age_ns")
    if not isinstance(value, int) or value <= 0:
        raise SemanticStateError("plan is missing a positive maximum_command_age_ns")
    return value


def observation_dependence(
    full: Trajectory, reduced: Trajectory
) -> dict[str, Any]:
    """Quantify how much of the derived state needs the instrumentation."""

    full_states = set(full.coverage.states)
    reduced_states = set(reduced.coverage.states)
    full_edges = set(full.coverage.edges)
    reduced_edges = set(reduced.coverage.edges)
    full_boundaries = set(full.coverage.contract_boundaries)
    reduced_boundaries = set(reduced.coverage.contract_boundaries)
    return {
        "full": {
            "steps": len(full.steps),
            "distinct_states": len(full_states),
            "distinct_edges": len(full_edges),
            "contract_boundaries": sorted(full_boundaries),
        },
        "reduced": {
            "steps": len(reduced.steps),
            "distinct_states": len(reduced_states),
            "distinct_edges": len(reduced_edges),
            "contract_boundaries": sorted(reduced_boundaries),
        },
        "lost_states": sorted(full_states - reduced_states),
        "lost_edges": sorted(full_edges - reduced_edges),
        "lost_contract_boundaries": sorted(full_boundaries - reduced_boundaries),
        "reduced_only_states": sorted(reduced_states - full_states),
        "final_state_equal": full.final_state.key() == reduced.final_state.key(),
        "lineage_observable_without_instrumentation": reduced.final_state.lineage
        != "none",
        "freshness_observable_without_instrumentation": reduced.final_state.freshness
        != "unknown",
    }
