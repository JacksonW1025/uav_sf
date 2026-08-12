#!/usr/bin/env python3
"""Close and classify one retained SITL attempt inside the frozen image."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts.collectors.closed_trace import close_trace
from scripts.collectors.ulog_route import ULogEvidenceError, inspect_ulog
from scripts.evaluator.evaluate_trace import evaluate
from scripts.evaluator.plan import load_plan
from scripts.model.runtime_route import read_trace
from scripts.runtime.artifacts import create_manifest


class ProcessingError(RuntimeError):
    """An attempt cannot be deterministically closed from its retained files."""


def _write_new(path: Path, value: Any) -> None:
    if path.exists():
        raise ProcessingError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _gazebo_metrics(path: Path) -> dict[str, Any]:
    values = [
        float(match.group(1))
        for match in re.finditer(
            r"^real_time_factor:\s*([-+0-9.eE]+)\s*$",
            path.read_text(encoding="utf-8", errors="replace"),
            re.MULTILINE,
        )
    ]
    # Startup and shutdown samples measure process orchestration, not stable
    # simulation throughput. Keep them in the raw stream but summarize the
    # central 80 percent for the concurrency qualification.
    ordered = sorted(values)
    trim = len(ordered) // 10
    central = ordered[trim : len(ordered) - trim] if trim and len(ordered) > 2 * trim else ordered
    return {
        "sample_count": len(values),
        "minimum": min(values) if values else None,
        "median": central[len(central) // 2] if central else None,
        "central_minimum": min(central) if central else None,
    }


def process_attempt(
    *,
    attempt_root: Path,
    plan_path: Path,
    environment_path: Path,
    maximum_clock_uncertainty_ns: int,
) -> dict[str, Any]:
    raw = attempt_root / "raw"
    derived = attempt_root / "derived"
    runtime_path = attempt_root / "runtime_result.json"
    if not raw.is_dir() or not runtime_path.is_file():
        raise ProcessingError("attempt raw directory or runtime result is missing")
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    plan = load_plan(plan_path)
    if runtime.get("run_id") != plan.get("run_id"):
        raise ProcessingError("runtime and plan run identities differ")
    derived.mkdir(exist_ok=False)
    raw_manifest = create_manifest(raw)
    _write_new(derived / "raw-evidence.manifest.json", raw_manifest)

    processing_error: str | None = None
    ulog_summary: dict[str, Any] | None = None
    evaluation: dict[str, Any] | None = None
    try:
        ulog_summary, observations = inspect_ulog(raw / "px4.ulg")
        _write_new(derived / "ulog-summary.json", ulog_summary)
        _write_new(derived / "route-observations.json", observations)
        if ulog_summary["status"] != "PASS":
            raise ProcessingError("ULog integrity rejected the source window")
        close_trace(
            plan_path=plan_path,
            environment_path=environment_path,
            ulog_summary_path=derived / "ulog-summary.json",
            observations_path=derived / "route-observations.json",
            sidecar_paths=[
                raw / "telemetry.sidecar.jsonl",
                raw / "workload.lifecycle.jsonl",
                raw / "runner.lifecycle.jsonl",
                raw / "gazebo.clock.jsonl",
            ],
            output_path=derived / "closed.trace.jsonl",
            maximum_clock_uncertainty_ns=maximum_clock_uncertainty_ns,
        )
        events = read_trace(derived / "closed.trace.jsonl")
        evaluation = evaluate(events, plan)
        _write_new(derived / "evaluation.json", evaluation)
    except (OSError, ValueError, ULogEvidenceError, ProcessingError) as exc:
        processing_error = str(exc)

    runtime_outcome = str(runtime.get("outcome"))
    if runtime_outcome in {
        "ENVIRONMENT_FAILURE",
        "CAMPAIGN_CONFIGURATION_FAILURE",
        "FORMAL_SAFETY_STOP",
        "TIMEOUT",
    }:
        outcome = runtime_outcome
    elif processing_error is not None:
        outcome = "OBSERVABILITY_REJECTED"
    elif evaluation is None or evaluation["evidence_gate"]["status"] != "ADMISSIBLE":
        outcome = "OBSERVABILITY_REJECTED"
    elif evaluation["status"] == "INCONCLUSIVE":
        outcome = "INCONCLUSIVE"
    else:
        # ACCEPTED means admissible empirical evidence. A SUT/Oracle
        # VIOLATION is intentionally accepted rather than retried away.
        outcome = "ACCEPTED"

    clock = None
    if (derived / "closed.trace.jsonl").is_file():
        for event in read_trace(derived / "closed.trace.jsonl"):
            if event.get("kind") == "clock_bridge":
                clock = event.get("bridge")
                break
    result = {
        "schema_version": "1.0",
        "study_id": runtime.get("allocation", {}).get("study_id", plan["plan_id"]),
        "attempt_id": plan["run_id"],
        "plan_id": plan["plan_id"],
        "outcome": outcome,
        "runtime_outcome": runtime_outcome,
        "evaluation_status": evaluation.get("status") if evaluation else None,
        "evidence_gate_status": (
            evaluation.get("evidence_gate", {}).get("status") if evaluation else None
        ),
        "processing_error": processing_error,
        "plan_digest": _sha256(plan_path),
        "environment_attestation_digest": _sha256(environment_path),
        "raw_manifest_digest": _sha256(derived / "raw-evidence.manifest.json"),
        "ulog": ulog_summary,
        "clock_bridge": clock,
        "gazebo": _gazebo_metrics(raw / "gazebo_stats.stdout.log"),
    }
    _write_new(attempt_root / "processing_result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--maximum-clock-uncertainty-ns", type=int, required=True)
    args = parser.parse_args()
    try:
        result = process_attempt(
            attempt_root=args.attempt_root,
            plan_path=args.plan,
            environment_path=args.environment,
            maximum_clock_uncertainty_ns=args.maximum_clock_uncertainty_ns,
        )
    except (OSError, ValueError, ProcessingError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["outcome"] == "ACCEPTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
