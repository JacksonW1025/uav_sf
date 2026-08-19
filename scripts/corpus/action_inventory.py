#!/usr/bin/env python3
"""Stage 2 candidate action and workload inventory.

`docs/EXPERIMENT_PLAN.md` requires an inventory along two axes before any core
corpus is frozen, and states that the number and identity of actions are
outputs of the analysis rather than assumptions.  This module therefore records
candidates, not a frozen corpus, and every declared candidate must survive
verification against the repository:

* each provenance path must exist;
* each referenced matrix cell must exist in that study's matrix;
* each live backend must be a wired action contract; and
* each declared contract boundary must exist in the semantic-state model.

Retained evidence is joined, never declared: launches and accepted counts come
from the study ledgers, and observed contract boundaries come from the Stage 1
semantic-state replay.  A candidate whose declared boundary is never observed
is reported as such instead of being quietly accepted.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from scripts.runtime.live_strategy_backend import CONTRACTS
from scripts.state.semantic_state import CONTRACT_BOUNDARIES


class InventoryError(RuntimeError):
    """A declared candidate cannot be verified against the repository."""


INVENTORY_ID = "stage2-action-corpus-inventory-v1"
DEFAULT_REPLAY_ROOT = Path("experiments/stage1_semantic_state_replay_v1")

# Axis 1, from the Stage 2 definition in docs/EXPERIMENT_PLAN.md.
LIFECYCLE_PHASES = (
    "registration",
    "activation",
    "execution",
    "completion",
    "replacement",
    "fallback",
    "re_entry",
)
# Axis 2.  `nominal` is not a failure mechanism; it labels the reachability and
# realism candidates that every failure candidate depends on.
MECHANISMS = (
    "nominal",
    "process_loss_restart",
    "setpoint_or_callback_stall",
    "communication_delay",
    "health_loss",
    "rejection",
    "manual_or_failsafe_takeover",
    "adjacent_authority_request",
)
ROLES = ("benchmark", "discovery", "realism_validation", "undecided")
KINDS = ("action", "workload")
INCLUSION = ("candidate", "gap")
ROUTE_MECHANISMS = ("legacy_offboard", "dynamic_external_mode", "mode_executor")


@dataclass(frozen=True)
class ActionCandidate:
    """One reviewable candidate for the eventual core corpus."""

    action_id: str
    kind: str
    summary: str
    lifecycle_phase: str
    mechanism: str
    route_mechanisms: tuple[str, ...]
    provenance: tuple[str, ...]
    matrix_cells: tuple[tuple[str, str], ...]
    preconditions: tuple[str, ...]
    cleanup: str
    expected_boundaries: tuple[str, ...]
    role: str
    role_basis: str
    observation_requirements: tuple[str, ...]
    inclusion: str
    inclusion_basis: str
    live_backend: str | None = None
    workload_profiles: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "kind": self.kind,
            "summary": self.summary,
            "lifecycle_phase": self.lifecycle_phase,
            "mechanism": self.mechanism,
            "route_mechanisms": list(self.route_mechanisms),
            "provenance": list(self.provenance),
            "matrix_cells": [
                {"study_id": study, "cell_id": cell} for study, cell in self.matrix_cells
            ],
            "live_backend": self.live_backend,
            "workload_profiles": list(self.workload_profiles),
            "preconditions": list(self.preconditions),
            "cleanup": self.cleanup,
            "expected_boundaries": list(self.expected_boundaries),
            "role": self.role,
            "role_basis": self.role_basis,
            "observation_requirements": list(self.observation_requirements),
            "inclusion": self.inclusion,
            "inclusion_basis": self.inclusion_basis,
        }


A1 = "motivation-thor-v1"
A1R = "motivation-thor-remediation-v1"
A2 = "motivation-stage-a2-thor-v1"
A2R = "motivation-stage-a2-thor-remediation-v1"
SLICE = "main-strategy-comparison-thor-v1"
EXIT = "main-process-exit-strategy-thor-v1"

RUN_SITL = "scripts/runtime/run_sitl.py"
OFFBOARD_NODE = "runtime/ros2/family_a_runtime/family_a_runtime/offboard_controller.py"
REQUESTER_NODE = (
    "runtime/ros2/family_a_runtime/family_a_runtime/external_mode_requester.py"
)
MANUAL_NODE = "runtime/ros2/family_a_runtime/family_a_runtime/manual_requester.py"
EXTERNAL_MODE = "runtime/ros2/family_a_modes/src/external_mode.cpp"
MODE_EXECUTOR = "runtime/ros2/family_a_modes/src/mode_executor.cpp"
MOVING_WORKLOAD = "scripts/runtime/moving_workload.py"
STRATEGY_BACKEND = "scripts/runtime/live_strategy_backend.py"


CANDIDATES: tuple[ActionCandidate, ...] = (
    ActionCandidate(
        action_id="register_external_mode",
        kind="action",
        summary="Register an external mode component and obtain a navigation slot.",
        lifecycle_phase="registration",
        mechanism="nominal",
        route_mechanisms=("dynamic_external_mode", "mode_executor"),
        provenance=(EXTERNAL_MODE, MODE_EXECUTOR, RUN_SITL),
        matrix_cells=((A1, "det-dynamic-trajectory-land"), (A1, "det-executor-completion-land")),
        preconditions=("a running external component with a reachable DDS session",),
        cleanup="unregister the component and leave no active producer session",
        expected_boundaries=(),
        role="realism_validation",
        role_basis=(
            "every dynamic external mode and mode executor transition depends on it; "
            "it is a precondition rather than a defect target"
        ),
        observation_requirements=(
            "registration events carrying registration identity and result code",
        ),
        inclusion="candidate",
        inclusion_basis="implemented, exercised by retained evidence in two studies",
    ),
    ActionCandidate(
        action_id="registration_capacity_rejection",
        kind="action",
        summary="Exhaust the external navigation-state slots so a further registration is refused.",
        lifecycle_phase="registration",
        mechanism="rejection",
        route_mechanisms=("dynamic_external_mode",),
        provenance=(RUN_SITL, EXTERNAL_MODE),
        matrix_cells=((A1, "fault-dynamic-registration-capacity"),),
        preconditions=("armed vehicle", "the primary external component already registered"),
        cleanup="stop every additional component and keep the primary session consistent",
        expected_boundaries=("registration_rejected",),
        role="benchmark",
        role_basis=(
            "a public capacity obligation with a deterministic rejection result code "
            "and retained accepted evidence"
        ),
        observation_requirements=(
            "registration result code, not merely the absence of an activation",
        ),
        inclusion="candidate",
        inclusion_basis="implemented with retained evidence; the rejection is a specified outcome",
    ),
    ActionCandidate(
        action_id="request_external_activation",
        kind="action",
        summary="Request the tested external route from a fully established internal source route.",
        lifecycle_phase="activation",
        mechanism="nominal",
        route_mechanisms=ROUTE_MECHANISMS,
        provenance=(OFFBOARD_NODE, REQUESTER_NODE, RUN_SITL),
        matrix_cells=(
            (A1, "det-offboard-trajectory-land"),
            (A1, "det-dynamic-trajectory-land"),
        ),
        preconditions=(
            "the source route is installed and has dwelled for its preregistered interval",
            "the producer prestream satisfies the public activation precondition",
        ),
        cleanup="release authority to a preregistered internal successor",
        expected_boundaries=("source_revoked", "target_installed"),
        role="realism_validation",
        role_basis="the transition under test; it carries the route and installation obligations",
        observation_requirements=(
            "activation and the four downstream lineage events under one route identity",
        ),
        inclusion="candidate",
        inclusion_basis="implemented, exercised in every retained study",
    ),
    ActionCandidate(
        action_id="activation_rejection_after_health_loss",
        kind="action",
        summary="Withhold the external mode health reply so the requested activation is refused.",
        lifecycle_phase="activation",
        mechanism="health_loss",
        route_mechanisms=("dynamic_external_mode",),
        provenance=(RUN_SITL, EXTERNAL_MODE, REQUESTER_NODE),
        matrix_cells=((A1, "fault-dynamic-health-loss"),),
        preconditions=("a registered external component", "an airborne internal source route"),
        cleanup="the vehicle must reach an internal safe route and disarm",
        expected_boundaries=("activation_rejected",),
        role="benchmark",
        role_basis=(
            "an explicit rejection obligation; lack of activation alone is not "
            "rejection evidence, so the fault marker is required"
        ),
        observation_requirements=(
            "an explicit rejection fault reason distinguishable from a silent non-activation",
        ),
        inclusion="candidate",
        inclusion_basis="implemented with retained evidence and a specified rejection outcome",
    ),
    ActionCandidate(
        action_id="owned_setpoint_stall_healthy",
        kind="action",
        summary="Stop the owned setpoint stream while the producer proof-of-life continues.",
        lifecycle_phase="execution",
        mechanism="setpoint_or_callback_stall",
        route_mechanisms=("legacy_offboard", "dynamic_external_mode"),
        provenance=(OFFBOARD_NODE, REQUESTER_NODE, STRATEGY_BACKEND),
        matrix_cells=(
            (A1, "fault-offboard-trajectory-stall"),
            (A2R, "a2-stall-offboard-remediation"),
            (A2R, "a2-stall-dynamic-remediation"),
            (SLICE, "main-offboard-state"),
            (SLICE, "main-dynamic-state"),
        ),
        live_backend="owned_setpoint_stall_v1",
        workload_profiles=("hover_constant", "straight_line"),
        preconditions=("the tested route is installed and consuming fresh commands",),
        cleanup="release to the preregistered successor and land",
        expected_boundaries=("command_stale",),
        role="benchmark",
        role_basis=(
            "a deliberate and reproducible freshness signature with a completed "
            "18-launch formal comparison and 16 retained moving-workload violations"
        ),
        observation_requirements=(
            "consumed command subject time across the whole target-authority window",
            "producer health separated from the setpoint stream",
        ),
        inclusion="candidate",
        inclusion_basis="implemented, live-wired, and the only action with a completed comparison",
    ),
    ActionCandidate(
        action_id="setpoint_kind_variation",
        kind="workload",
        summary="Drive the tested route through position, attitude, or body-rate setpoints.",
        lifecycle_phase="execution",
        mechanism="nominal",
        route_mechanisms=("legacy_offboard",),
        provenance=(OFFBOARD_NODE,),
        matrix_cells=(
            (A1, "det-offboard-attitude-land"),
            (A1, "det-offboard-body-rate-land"),
            (A1, "fault-offboard-attitude-stall"),
            (A1, "fault-offboard-body-rate-stall"),
        ),
        workload_profiles=("hover_constant",),
        preconditions=(
            "an airborne vehicle established by public actions before the tested request",
        ),
        cleanup="release to the preregistered successor and land",
        expected_boundaries=("target_installed",),
        role="discovery",
        role_basis=(
            "the retained attitude-path installation signatures are localized but not "
            "source-attributed, so this variant selects an unexplained region"
        ),
        observation_requirements=(
            "controller and allocator identity per setpoint kind",
            "a physical-validity contract, because these cells produced the "
            "non-airborne stratum in the Stage A1 audit",
        ),
        inclusion="candidate",
        inclusion_basis="implemented with retained evidence and an open question attached",
    ),
    ActionCandidate(
        action_id="communication_delay_or_reconnect",
        kind="action",
        summary="Delay or briefly interrupt the producer transport without stopping the producer.",
        lifecycle_phase="execution",
        mechanism="communication_delay",
        route_mechanisms=("legacy_offboard", "dynamic_external_mode"),
        provenance=(RUN_SITL,),
        matrix_cells=(),
        preconditions=("the tested route is installed and consuming fresh commands",),
        cleanup="restore the transport and reach an internal safe route",
        expected_boundaries=("command_stale",),
        role="undecided",
        role_basis=(
            "no implementation and no retained evidence; whether it adds a signature "
            "beyond the owned stall is unknown"
        ),
        observation_requirements=(
            "a controlled transport delay with a recorded applied schedule",
            "consumed command age separated from producer liveness",
            "evidence that the delay, not scheduler jitter, produced the age",
        ),
        inclusion="gap",
        inclusion_basis="named by the method action grammar but not implemented or qualified",
    ),
    ActionCandidate(
        action_id="nominal_completion_release",
        kind="action",
        summary="Complete the tested route and request the preregistered internal successor.",
        lifecycle_phase="completion",
        mechanism="nominal",
        route_mechanisms=("legacy_offboard", "dynamic_external_mode"),
        provenance=(OFFBOARD_NODE, REQUESTER_NODE),
        matrix_cells=(
            (A1, "det-offboard-trajectory-hold"),
            (A1, "det-offboard-trajectory-rtl"),
            (A2R, "a2-normal-offboard-remediation"),
            (A2R, "a2-normal-dynamic-remediation"),
        ),
        workload_profiles=("hover_constant", "straight_line"),
        preconditions=("the tested route is installed and executing",),
        cleanup="the successor must be completely installed before landing",
        expected_boundaries=("successor_requested", "successor_installed"),
        role="realism_validation",
        role_basis="establishes the nominal reference against which fault arms are read",
        observation_requirements=("successor installation under one route identity",),
        inclusion="candidate",
        inclusion_basis="implemented, exercised in four retained studies",
    ),
    ActionCandidate(
        action_id="mode_executor_completion",
        kind="action",
        summary="Let a mode executor complete its owned mode and hand over to its successor.",
        lifecycle_phase="completion",
        mechanism="nominal",
        route_mechanisms=("mode_executor",),
        provenance=(MODE_EXECUTOR,),
        matrix_cells=((A1, "det-executor-completion-land"),),
        preconditions=("a registered executor owning the tested mode",),
        cleanup="the executor must release ownership and the successor must install",
        expected_boundaries=("successor_installed",),
        role="realism_validation",
        role_basis="covers executor ownership, which the other mechanisms do not exercise",
        observation_requirements=("lifecycle owner and executor owner separately",),
        inclusion="candidate",
        inclusion_basis="implemented with retained evidence",
    ),
    ActionCandidate(
        action_id="adjacent_land_request_near_completion",
        kind="action",
        summary="Issue an adjacent internal Land request just before, at, or after completion.",
        lifecycle_phase="replacement",
        mechanism="adjacent_authority_request",
        route_mechanisms=("mode_executor",),
        provenance=(MANUAL_NODE, RUN_SITL),
        matrix_cells=(
            (A1, "timing-executor-before"),
            (A1, "timing-executor-near"),
            (A1, "timing-executor-after"),
            (A1R, "timing-executor-before-remediation"),
        ),
        preconditions=("an executor-owned mode approaching its completion boundary",),
        cleanup="one successor must win and install completely",
        expected_boundaries=("successor_installed",),
        role="discovery",
        role_basis=(
            "retained evidence shows request timing and order leaving the frozen bucket "
            "while the successor still installed, which no terminal outcome would show"
        ),
        observation_requirements=(
            "adjacent request time anchored to the transition, not to wall clock",
        ),
        inclusion="candidate",
        inclusion_basis="implemented across three timing buckets with retained evidence",
    ),
    ActionCandidate(
        action_id="manual_or_gcs_takeover",
        kind="action",
        summary="Take authority through an operator or ground-station request during execution.",
        lifecycle_phase="replacement",
        mechanism="manual_or_failsafe_takeover",
        route_mechanisms=("legacy_offboard", "dynamic_external_mode"),
        provenance=(MANUAL_NODE,),
        matrix_cells=(),
        preconditions=("the tested route is installed and executing",),
        cleanup="the taking route must install completely and reach a safe terminal state",
        expected_boundaries=("source_revoked", "target_installed"),
        role="undecided",
        role_basis="no operator or ground-station channel is implemented in the harness",
        observation_requirements=(
            "an operator request path distinguishable from the adjacent internal request",
        ),
        inclusion="gap",
        inclusion_basis="named by the method action grammar; only the adjacent internal request exists",
    ),
    ActionCandidate(
        action_id="concurrent_external_producers",
        kind="action",
        summary="Run two external producers that contend for the same authority.",
        lifecycle_phase="replacement",
        mechanism="adjacent_authority_request",
        route_mechanisms=("dynamic_external_mode",),
        provenance=(EXTERNAL_MODE,),
        matrix_cells=(),
        preconditions=("two registered components with distinct sessions",),
        cleanup="exactly one writer must remain and the other must be released",
        expected_boundaries=("target_installed",),
        role="undecided",
        role_basis=(
            "the capacity cell registers extra components but never lets a second "
            "producer contend for an installed route"
        ),
        observation_requirements=("writer exclusivity across two producer sessions",),
        inclusion="gap",
        inclusion_basis="not implemented; distinct from the registration capacity action",
    ),
    ActionCandidate(
        action_id="owned_process_exit_fallback",
        kind="action",
        summary="Terminate the owning external producer and require a safe internal fallback.",
        lifecycle_phase="fallback",
        mechanism="process_loss_restart",
        route_mechanisms=("legacy_offboard", "dynamic_external_mode"),
        provenance=(OFFBOARD_NODE, REQUESTER_NODE, STRATEGY_BACKEND),
        matrix_cells=(
            (A1, "fault-offboard-process-exit"),
            (A1, "fault-dynamic-process-exit"),
            (EXIT, "main-process-exit-offboard-state"),
            (EXIT, "main-process-exit-dynamic-state"),
        ),
        live_backend="owned_process_exit_fallback_v1",
        workload_profiles=("hover_constant", "straight_line"),
        preconditions=("the tested route is installed and the producer owns it",),
        cleanup="a complete internal safe route must install without operator action",
        expected_boundaries=("fallback_installed",),
        role="benchmark",
        role_basis=(
            "a specified failsafe obligation with retained Stage A1 evidence and a "
            "passing non-formal qualification of the live backend"
        ),
        observation_requirements=(
            "producer session end distinguished from a stalled stream",
            "complete fallback installation, not merely a safe mode label",
        ),
        inclusion="candidate",
        inclusion_basis=(
            "implemented and live-wired; its preregistered matrix has zero formal "
            "launches and is not authorized by readiness alone"
        ),
    ),
    ActionCandidate(
        action_id="producer_restart_after_exit",
        kind="action",
        summary="Restart the producer after a loss and attempt to reclaim authority.",
        lifecycle_phase="fallback",
        mechanism="process_loss_restart",
        route_mechanisms=("legacy_offboard", "dynamic_external_mode"),
        provenance=(REQUESTER_NODE,),
        matrix_cells=(),
        preconditions=("an already installed fallback route after a producer loss",),
        cleanup="either the reclaim installs completely or the safe route is retained",
        expected_boundaries=("target_installed",),
        role="undecided",
        role_basis="only the loss is implemented; reclaim after loss has no fixture",
        observation_requirements=(
            "a new producer session identity distinct from the lost one",
        ),
        inclusion="gap",
        inclusion_basis="named by the method action grammar but not implemented",
    ),
    ActionCandidate(
        action_id="failsafe_takeover",
        kind="action",
        summary="Trigger an internal failsafe condition that replaces the tested route.",
        lifecycle_phase="fallback",
        mechanism="manual_or_failsafe_takeover",
        route_mechanisms=("legacy_offboard", "dynamic_external_mode"),
        provenance=(RUN_SITL,),
        matrix_cells=(),
        preconditions=("the tested route is installed and executing",),
        cleanup="the failsafe route must install completely and terminate safely",
        expected_boundaries=("fallback_installed",),
        role="undecided",
        role_basis=(
            "the harness disables only the absent power and datalink interfaces; no "
            "failsafe condition is deliberately induced"
        ),
        observation_requirements=(
            "the failsafe trigger source recorded as an action, not inferred afterwards",
            "safety limits that separate an induced failsafe from a supervisor stop",
        ),
        inclusion="gap",
        inclusion_basis="not implemented; would need its own safety qualification",
    ),
    ActionCandidate(
        action_id="route_re_entry_through_hold",
        kind="action",
        summary="Leave the tested route to internal Hold and enter it again in one attempt.",
        lifecycle_phase="re_entry",
        mechanism="nominal",
        route_mechanisms=("legacy_offboard",),
        provenance=(OFFBOARD_NODE,),
        matrix_cells=((A1, "timing-offboard-reentry-hold"),),
        preconditions=("a completed first entry and a re-established prestream",),
        cleanup="the final entry must release to a landing successor",
        expected_boundaries=("target_installed", "source_revoked"),
        role="benchmark",
        role_basis=(
            "two successful entries under one route name can only be separated by "
            "epoch and activation identity, which is the representation claim"
        ),
        observation_requirements=("route epoch and activation identity per entry",),
        inclusion="candidate",
        inclusion_basis="implemented with retained evidence",
    ),
    ActionCandidate(
        action_id="route_re_entry_through_rtl",
        kind="action",
        summary="Leave the tested route to internal RTL and enter it again in one attempt.",
        lifecycle_phase="re_entry",
        mechanism="nominal",
        route_mechanisms=("legacy_offboard",),
        provenance=(OFFBOARD_NODE,),
        matrix_cells=(
            (A1, "timing-offboard-reentry-rtl"),
            (A1R, "timing-offboard-reentry-rtl-remediation"),
        ),
        preconditions=(
            "an airborne RTL source established by public arm, takeoff and RTL requests",
        ),
        cleanup="the final entry must release to a landing successor",
        expected_boundaries=("target_installed", "source_revoked"),
        role="benchmark",
        role_basis=(
            "the same identity claim as the Hold variant, and its primary cell is the "
            "worked example of an unreachable fixture obligation"
        ),
        observation_requirements=("route epoch and activation identity per entry",),
        inclusion="candidate",
        inclusion_basis=(
            "implemented; the primary cell reached its cap with no accepted evidence "
            "and an independent remediation supplied it"
        ),
    ),
)


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _write_new(path: Path, text: str) -> None:
    if path.exists():
        raise InventoryError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise InventoryError(f"non-object JSON at {path}:{number}")
        values.append(value)
    return values


@dataclass
class _StudyIndex:
    """Matrix cells and closed-attempt counts for every retained study."""

    cells: dict[str, set[str]] = field(default_factory=dict)
    ledger: dict[tuple[str, str], dict[str, int]] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)


def _index_studies(root: Path) -> _StudyIndex:
    index = _StudyIndex()
    for directory in sorted((root / "experiments").iterdir()):
        matrix_path = directory / "matrix.json"
        if not matrix_path.is_file():
            continue
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        study_id = str(matrix["study_id"])
        index.cells[study_id] = {str(cell["cell_id"]) for cell in matrix["cells"]}
        index.sources[str(matrix_path.relative_to(root))] = _digest(matrix_path)
        ledger_path = directory / "attempt-ledger.jsonl"
        if not ledger_path.is_file():
            continue
        index.sources[str(ledger_path.relative_to(root))] = _digest(ledger_path)
        for event in _read_jsonl(ledger_path):
            if event.get("state") != "CLOSED":
                continue
            key = (study_id, str(event.get("cell_id", "")))
            counts = index.ledger.setdefault(key, {"launches": 0, "accepted": 0})
            counts["launches"] += 1
            if event.get("payload", {}).get("outcome") == "ACCEPTED":
                counts["accepted"] += 1
    if not index.cells:
        raise InventoryError("no study matrix was found")
    return index


def _observed_boundaries(replay_root: Path) -> dict[tuple[str, str], set[str]]:
    per_attempt = replay_root / "per-attempt.jsonl"
    if not per_attempt.is_file():
        raise InventoryError(
            "the Stage 1 semantic-state replay is required before this inventory: "
            f"{per_attempt} is missing"
        )
    observed: dict[tuple[str, str], set[str]] = {}
    for record in _read_jsonl(per_attempt):
        key = (str(record["study_id"]), str(record["cell_id"]))
        observed.setdefault(key, set()).update(record["coverage"]["contract_boundaries"])
    return observed


def _verify(candidate: ActionCandidate, root: Path, index: _StudyIndex) -> None:
    if candidate.lifecycle_phase not in LIFECYCLE_PHASES:
        raise InventoryError(f"{candidate.action_id}: unsupported lifecycle phase")
    if candidate.mechanism not in MECHANISMS:
        raise InventoryError(f"{candidate.action_id}: unsupported mechanism")
    if candidate.role not in ROLES:
        raise InventoryError(f"{candidate.action_id}: unsupported role")
    if candidate.kind not in KINDS:
        raise InventoryError(f"{candidate.action_id}: unsupported kind")
    if candidate.inclusion not in INCLUSION:
        raise InventoryError(f"{candidate.action_id}: unsupported inclusion")
    for route in candidate.route_mechanisms:
        if route not in ROUTE_MECHANISMS:
            raise InventoryError(f"{candidate.action_id}: unsupported route mechanism {route}")
    for boundary in candidate.expected_boundaries:
        if boundary not in CONTRACT_BOUNDARIES:
            raise InventoryError(f"{candidate.action_id}: unknown boundary {boundary}")
    for relative in candidate.provenance:
        if not (root / relative).exists():
            raise InventoryError(f"{candidate.action_id}: missing provenance {relative}")
    for study_id, cell_id in candidate.matrix_cells:
        if study_id not in index.cells:
            raise InventoryError(f"{candidate.action_id}: unknown study {study_id}")
        if cell_id not in index.cells[study_id]:
            raise InventoryError(f"{candidate.action_id}: unknown cell {study_id}/{cell_id}")
    if candidate.live_backend is not None and candidate.live_backend not in CONTRACTS:
        raise InventoryError(f"{candidate.action_id}: unwired backend {candidate.live_backend}")
    if candidate.inclusion == "gap" and candidate.matrix_cells:
        raise InventoryError(f"{candidate.action_id}: a gap must not claim matrix cells")
    if candidate.inclusion == "candidate" and not candidate.matrix_cells:
        raise InventoryError(f"{candidate.action_id}: a candidate requires a matrix cell")


def build_inventory(root: Path, *, replay_root: Path) -> dict[str, Any]:
    root = root.resolve()
    index = _index_studies(root)
    observed = _observed_boundaries(replay_root if replay_root.is_absolute() else root / replay_root)

    records: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for candidate in CANDIDATES:
        if candidate.action_id in identifiers:
            raise InventoryError(f"duplicate action identity: {candidate.action_id}")
        identifiers.add(candidate.action_id)
        _verify(candidate, root, index)
        launches = 0
        accepted = 0
        seen: set[str] = set()
        cells: list[dict[str, Any]] = []
        for study_id, cell_id in candidate.matrix_cells:
            counts = index.ledger.get((study_id, cell_id), {"launches": 0, "accepted": 0})
            boundaries = sorted(observed.get((study_id, cell_id), set()))
            launches += counts["launches"]
            accepted += counts["accepted"]
            seen.update(boundaries)
            cells.append(
                {
                    "study_id": study_id,
                    "cell_id": cell_id,
                    "launches": counts["launches"],
                    "accepted": counts["accepted"],
                    "observed_contract_boundaries": boundaries,
                }
            )
        record = candidate.as_dict()
        record["evidence"] = {
            "cells": cells,
            "launches": launches,
            "accepted": accepted,
            "observed_contract_boundaries": sorted(seen),
            "expected_boundaries_not_observed": sorted(
                set(candidate.expected_boundaries) - seen
            ),
            "implemented": candidate.inclusion == "candidate",
            "live_backend_wired": candidate.live_backend is not None,
        }
        records.append(record)

    axis_matrix: list[dict[str, Any]] = []
    for phase in LIFECYCLE_PHASES:
        for mechanism in MECHANISMS:
            matching = [
                record
                for record in records
                if record["lifecycle_phase"] == phase and record["mechanism"] == mechanism
            ]
            if not matching:
                continue
            axis_matrix.append(
                {
                    "lifecycle_phase": phase,
                    "mechanism": mechanism,
                    "action_ids": [record["action_id"] for record in matching],
                    "with_retained_evidence": [
                        record["action_id"]
                        for record in matching
                        if record["evidence"]["accepted"] > 0
                    ],
                    "gaps": [
                        record["action_id"]
                        for record in matching
                        if record["inclusion"] == "gap"
                    ],
                }
            )

    covered_pairs = {
        (entry["lifecycle_phase"], entry["mechanism"])
        for entry in axis_matrix
        if entry["with_retained_evidence"]
    }
    declared_boundaries = {
        boundary for record in records for boundary in record["expected_boundaries"]
    }
    observed_boundaries = {
        boundary
        for record in records
        for boundary in record["evidence"]["observed_contract_boundaries"]
    }
    return {
        "schema_version": "1.0",
        "inventory_id": INVENTORY_ID,
        "frozen": False,
        "freeze_rule": (
            "Stage 2 freezes a minimal representative corpus only after this "
            "inventory is reviewed; this artifact is the inventory, not the corpus"
        ),
        "axes": {
            "lifecycle_phases": list(LIFECYCLE_PHASES),
            "mechanisms": list(MECHANISMS),
        },
        "totals": {
            "candidates": sum(1 for record in records if record["inclusion"] == "candidate"),
            "gaps": sum(1 for record in records if record["inclusion"] == "gap"),
            "with_retained_evidence": sum(
                1 for record in records if record["evidence"]["accepted"] > 0
            ),
            "with_live_backend": sum(
                1 for record in records if record["live_backend"] is not None
            ),
            "roles": {
                role: sum(1 for record in records if record["role"] == role)
                for role in ROLES
            },
        },
        "axis_matrix": axis_matrix,
        "axis_pairs_without_evidence": [
            {"lifecycle_phase": phase, "mechanism": mechanism}
            for phase in LIFECYCLE_PHASES
            for mechanism in MECHANISMS
            if any(
                entry["lifecycle_phase"] == phase and entry["mechanism"] == mechanism
                for entry in axis_matrix
            )
            and (phase, mechanism) not in covered_pairs
        ],
        "boundaries": {
            "declared": sorted(declared_boundaries),
            "observed": sorted(observed_boundaries),
            "declared_not_observed": sorted(declared_boundaries - observed_boundaries),
            "model_boundaries_no_candidate_declares": sorted(
                set(CONTRACT_BOUNDARIES) - declared_boundaries
            ),
        },
        "actions": records,
        "sources": dict(sorted(index.sources.items())),
    }


def run(root: Path, output_root: Path, *, replay_root: Path) -> dict[str, Any]:
    output_root = output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise InventoryError(f"output directory is not empty: {output_root}")
    inventory = build_inventory(root, replay_root=replay_root)
    _write_new(
        output_root / "inventory.json",
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
    )
    summary = {
        "schema_version": "1.0",
        "inventory_id": INVENTORY_ID,
        "frozen": inventory["frozen"],
        "totals": inventory["totals"],
        "axis_pairs_without_evidence": inventory["axis_pairs_without_evidence"],
        "boundaries": inventory["boundaries"],
    }
    _write_new(
        output_root / "summary.json", json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--replay-root", type=Path, default=DEFAULT_REPLAY_ROOT)
    args = parser.parse_args()
    try:
        summary = run(args.root, args.output_root, replay_root=args.replay_root)
    except (InventoryError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": "PASS", "summary": summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
