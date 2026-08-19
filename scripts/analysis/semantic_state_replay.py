#!/usr/bin/env python3
"""Replay the semantic-state extractor over every retained admissible trace.

This is a read-only Stage 1 analysis.  It never edits a closed trace, a frozen
evaluation, a matrix or a ledger, and it produces no new formal denominator.
It answers three mechanical questions:

1. does equivalent retained evidence produce an identical derived trajectory;
2. does the derived state distinguish route epoch, authority owner, lifecycle
   progress and command freshness without any declared-mode label; and
3. how much of that state survives when the repository observability
   instrumentation is removed from the input.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from scripts.accounting.study import verify_study_ledger
from scripts.model.runtime_route import read_trace
from scripts.state.semantic_state import (
    CONTRACT_BOUNDARIES,
    LIFECYCLE_PHASES,
    MODE_LABEL_FIELDS,
    SemanticStateError,
    derive_trajectory,
    maximum_command_age_from_plan,
    mode_label_fields,
    observation_dependence,
    public_events,
    with_perturbed_mode_labels,
    without_mode_labels,
)


class ReplayError(RuntimeError):
    """The retained corpus cannot support the registered replay analysis."""


ANALYSIS_ID = "stage1-semantic-state-replay-v1"
REQUIRED_PHASES = (
    "idle",
    "activation_requested",
    "activated",
    "executing",
    "completed",
    "replacing",
    "terminal",
)


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _write_new(path: Path, text: str) -> None:
    if path.exists():
        raise ReplayError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _accepted_attempts(ledger: Path) -> list[dict[str, Any]]:
    verify_study_ledger(ledger)
    accepted: list[dict[str, Any]] = []
    seen: set[str] = set()
    for number, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("state") != "CLOSED":
            continue
        attempt_id = str(event.get("attempt_id", ""))
        if not attempt_id:
            raise ReplayError(f"empty attempt identity at {ledger}:{number}")
        if attempt_id in seen:
            raise ReplayError(f"duplicate CLOSED attempt at {ledger}:{number}")
        seen.add(attempt_id)
        if event.get("payload", {}).get("outcome") != "ACCEPTED":
            continue
        accepted.append(event)
    return accepted


def discover_studies(root: Path) -> list[tuple[str, Path]]:
    """Every retained study directory that closed at least one attempt."""

    studies: list[tuple[str, Path]] = []
    for directory in sorted((root / "experiments").iterdir()):
        ledger = directory / "attempt-ledger.jsonl"
        if not ledger.is_file():
            continue
        first = next(
            (
                line
                for line in ledger.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ),
            None,
        )
        if first is None:
            raise ReplayError(f"empty attempt ledger: {ledger}")
        study_id = str(json.loads(first).get("study_id", ""))
        if not study_id:
            raise ReplayError(f"ledger has no study identity: {ledger}")
        studies.append((study_id, directory))
    if not studies:
        raise ReplayError("no retained study ledger was found")
    return studies


def _attempt_inputs(
    root: Path, study_id: str, attempt_id: str
) -> tuple[Path, Path]:
    plan = root / "runs" / study_id / "plans" / f"{attempt_id}.json"
    trace = root / "runs" / study_id / attempt_id / "derived" / "closed.trace.jsonl"
    missing = [path for path in (plan, trace) if not path.is_file()]
    if missing:
        raise ReplayError(
            f"{study_id}/{attempt_id} is missing retained inputs: "
            + ", ".join(str(path) for path in missing)
        )
    return plan, trace


def replay_attempt(
    root: Path, study_id: str, attempt_id: str, cell_id: str
) -> dict[str, Any]:
    plan_path, trace_path = _attempt_inputs(root, study_id, attempt_id)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    bound = maximum_command_age_from_plan(plan)

    events = read_trace(trace_path)
    trajectory = derive_trajectory(events, maximum_command_age_ns=bound)
    # Determinism is checked against an independent parse of the same retained
    # file, not against a cached in-memory event list.
    repeated = derive_trajectory(read_trace(trace_path), maximum_command_age_ns=bound)
    reduced = derive_trajectory(public_events(events), maximum_command_age_ns=bound)
    # A declared mode is an observation field in the evidence.  Removing it and
    # replacing it with an impossible value must both leave the derived
    # trajectory untouched, which is stronger than asserting it is unused.
    stripped = derive_trajectory(
        without_mode_labels(events), maximum_command_age_ns=bound
    )
    perturbed = derive_trajectory(
        with_perturbed_mode_labels(events), maximum_command_age_ns=bound
    )

    coverage = trajectory.coverage
    final = trajectory.final_state
    epochs_per_route: Counter[str] = Counter()
    for step in trajectory.steps:
        if step.state.route is not None and step.state.route_epoch is not None:
            epochs_per_route[step.state.route] = max(
                epochs_per_route[step.state.route], step.state.route_epoch_index
            )
    return {
        "study_id": study_id,
        "attempt_id": attempt_id,
        "cell_id": cell_id,
        "inputs": {
            "plan": str(plan_path.relative_to(root)),
            "trace": str(trace_path.relative_to(root)),
            "digests": {"plan": _digest(plan_path), "trace": _digest(trace_path)},
            "maximum_command_age_ns": bound,
        },
        "events": {
            "total": len(events),
            "instrumented": trajectory.instrumented_events,
            "public": trajectory.public_events,
            "mode_label_fields_present": mode_label_fields(events),
        },
        "trajectory": {
            "steps": len(trajectory.steps),
            "digest": trajectory.digest(),
            "repeated_digest": repeated.digest(),
            "deterministic": trajectory.digest() == repeated.digest(),
            "mode_label_independent": (
                trajectory.digest() == stripped.digest()
                and trajectory.digest() == perturbed.digest()
            ),
            "final_state_key": final.key(),
            "maximum_route_epoch_index": dict(sorted(epochs_per_route.items())),
        },
        "coverage": {
            "distinct_states": len(coverage.states),
            "distinct_edges": len(coverage.edges),
            "states": sorted(coverage.states),
            "edges": sorted(coverage.edges),
            "phases": sorted(coverage.phases),
            "actions": sorted(coverage.actions),
            "contract_boundaries": sorted(coverage.contract_boundaries),
        },
        "observation_dependence": observation_dependence(trajectory, reduced),
    }


def _analysis_plan(root: Path, studies: list[tuple[str, Path]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "analysis_id": ANALYSIS_ID,
        "analysis_kind": "read_only_posthoc",
        "purpose": (
            "Replay the deterministic semantic-state extractor over retained "
            "admissible traces and quantify instrumentation dependence."
        ),
        "state_schema": "data/schemas/semantic_state.schema.json",
        "extractor": "scripts/state/semantic_state.py",
        "inputs": [
            {
                "study_id": study_id,
                "ledger": str((directory / "attempt-ledger.jsonl").relative_to(root)),
                "ledger_digest": _digest(directory / "attempt-ledger.jsonl"),
            }
            for study_id, directory in studies
        ],
        "decision_rules": {
            "selected_attempts": "every CLOSED attempt whose outcome is ACCEPTED",
            "freshness_bound": "the maximum_command_age_ns frozen in each attempt plan",
            "determinism_check": "re-parse the retained trace and re-derive",
            "reduced_observation_rule": (
                "drop every event carrying raw_source_domain, which is exactly "
                "the evidence produced by the tracked observability patches"
            ),
            "mode_label_rule": (
                "re-derive with every declared-mode field removed and with it "
                "replaced by an impossible sentinel; both trajectories must "
                "equal the original"
            ),
            "mutates_frozen_evidence": False,
            "creates_formal_denominator": False,
        },
        "mode_label_fields": list(MODE_LABEL_FIELDS),
        "required_phases": list(REQUIRED_PHASES),
        "contract_boundaries": list(CONTRACT_BOUNDARIES),
        "lifecycle_phases": list(LIFECYCLE_PHASES),
    }


def run(root: Path, output_root: Path, *, selected: list[str] | None = None) -> dict[str, Any]:
    root = root.resolve()
    output_root = output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise ReplayError(f"output directory is not empty: {output_root}")

    studies = discover_studies(root)
    if selected:
        known = {study_id for study_id, _ in studies}
        unknown = sorted(set(selected) - known)
        if unknown:
            raise ReplayError("unknown study identity: " + ", ".join(unknown))
        studies = [item for item in studies if item[0] in set(selected)]

    records: list[dict[str, Any]] = []
    for study_id, directory in studies:
        for event in _accepted_attempts(directory / "attempt-ledger.jsonl"):
            records.append(
                replay_attempt(
                    root,
                    study_id,
                    str(event["attempt_id"]),
                    str(event.get("cell_id", "")),
                )
            )
    if not records:
        raise ReplayError("no accepted attempt was available for replay")

    states: Counter[str] = Counter()
    edges: Counter[str] = Counter()
    phases: Counter[str] = Counter()
    actions: Counter[str] = Counter()
    boundaries: Counter[str] = Counter()
    final_states: Counter[str] = Counter()
    per_study: dict[str, int] = {}
    freshness_states: set[str] = set()
    owner_classes: set[str] = set()
    fault_classes: set[str] = set()
    motion_phases: set[str] = set()
    reentry_attempts = 0
    lineage_survivors = 0
    freshness_survivors = 0
    boundary_survivors = 0
    equal_final_state = 0
    mode_label_attempts = 0
    non_deterministic: list[str] = []
    mode_label_dependent: list[str] = []

    def _classify(state_key: str) -> None:
        for part in state_key.split("|"):
            name, _, value = part.partition("=")
            if name == "freshness":
                freshness_states.add(value)
            elif name == "owner":
                owner_classes.add(value)
            elif name == "fault":
                fault_classes.add(value)
            elif name == "motion":
                motion_phases.add(value)

    for record in records:
        per_study[record["study_id"]] = per_study.get(record["study_id"], 0) + 1
        if not record["trajectory"]["deterministic"]:
            non_deterministic.append(record["attempt_id"])
        if record["events"]["mode_label_fields_present"]:
            mode_label_attempts += 1
        if not record["trajectory"]["mode_label_independent"]:
            mode_label_dependent.append(record["attempt_id"])
        if any(
            index >= 2
            for index in record["trajectory"]["maximum_route_epoch_index"].values()
        ):
            reentry_attempts += 1
        for name in record["coverage"]["phases"]:
            phases[name] += 1
        for name in record["coverage"]["actions"]:
            actions[name] += 1
        for name in record["coverage"]["contract_boundaries"]:
            boundaries[name] += 1
        for state_key in record["coverage"]["states"]:
            states[state_key] += 1
            _classify(state_key)
        for edge in record["coverage"]["edges"]:
            edges[edge] += 1
        final_states[record["trajectory"]["final_state_key"]] += 1
        dependence = record["observation_dependence"]
        lineage_survivors += int(dependence["lineage_observable_without_instrumentation"])
        freshness_survivors += int(
            dependence["freshness_observable_without_instrumentation"]
        )
        boundary_survivors += int(bool(dependence["reduced"]["contract_boundaries"]))
        equal_final_state += int(dependence["final_state_equal"])

    observed_phases = set(phases)
    exit_criteria = {
        "deterministic_replay": not non_deterministic,
        "ignores_mode_labels": not mode_label_dependent,
        "distinguishes_route_epoch": reentry_attempts > 0,
        "distinguishes_owner": {"internal", "external"} <= owner_classes,
        "distinguishes_lifecycle_progress": set(REQUIRED_PHASES) <= observed_phases,
        "distinguishes_command_freshness": {"fresh", "stale"} <= freshness_states,
    }
    summary = {
        "schema_version": "1.0",
        "analysis_id": ANALYSIS_ID,
        "attempts_replayed": len(records),
        "attempts_per_study": dict(sorted(per_study.items())),
        "non_deterministic_attempts": sorted(non_deterministic),
        "mode_label_dependent_attempts": sorted(mode_label_dependent),
        "attempts_with_mode_label_fields_in_evidence": mode_label_attempts,
        "corpus_coverage": {
            "distinct_semantic_states": len(states),
            "distinct_semantic_edges": len(edges),
            "distinct_final_state_keys": len(final_states),
            "distinct_lifecycle_phases": sorted(observed_phases),
            "distinct_actions": sorted(actions),
            "distinct_contract_boundaries": sorted(boundaries),
            "observed_freshness_states": sorted(freshness_states),
            "observed_owner_classes": sorted(owner_classes),
            "observed_fault_classes": sorted(fault_classes),
            "observed_motion_phases": sorted(motion_phases),
            "attempts_per_contract_boundary": dict(sorted(boundaries.items())),
            "attempts_per_action": dict(sorted(actions.items())),
            "attempts_with_route_re_entry": reentry_attempts,
        },
        "reduced_observation": {
            "attempts": len(records),
            "attempts_retaining_command_lineage": lineage_survivors,
            "attempts_retaining_command_freshness": freshness_survivors,
            "attempts_retaining_any_contract_boundary": boundary_survivors,
            "attempts_with_equal_final_state": equal_final_state,
        },
        "exit_criteria": exit_criteria,
        "exit_criteria_met": all(exit_criteria.values()),
        "immutability": {
            "modified_frozen_evidence": False,
            "created_formal_denominator": False,
        },
    }

    _write_new(
        output_root / "analysis-plan.json",
        json.dumps(_analysis_plan(root, studies), indent=2, sort_keys=True) + "\n",
    )
    _write_new(
        output_root / "input-manifest.json",
        json.dumps(
            {
                "schema_version": "1.0",
                "analysis_id": ANALYSIS_ID,
                "attempts": [
                    {
                        "study_id": record["study_id"],
                        "attempt_id": record["attempt_id"],
                        "cell_id": record["cell_id"],
                        **record["inputs"],
                    }
                    for record in records
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    _write_new(
        output_root / "per-attempt.jsonl",
        "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in records
        ),
    )
    _write_new(
        output_root / "summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--study",
        action="append",
        default=None,
        help="restrict the replay to one retained study identity (repeatable)",
    )
    args = parser.parse_args()
    try:
        summary = run(args.root, args.output_root, selected=args.study)
    except (
        ReplayError,
        SemanticStateError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": "PASS", "summary": summary}, sort_keys=True))
    return 0 if summary["exit_criteria_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
