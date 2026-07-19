#!/usr/bin/env python3
"""Classify the single preregistered Issue #162 replay on the current lock."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_EXCEPTION = (
    "A mode executor cannot be used in combination with a mode that replaces an "
    "internal mode. See https://github.com/PX4/PX4-Autopilot/issues/25707"
)
P5_GATE = ROOT / "experiments/probes/p5/p5_v6_differential_gate.json"
P5_MANIFEST = ROOT / "experiments/probes/p5/campaign_seeded_v6_manifest.json"
P5_GATE_SHA256 = "9542eb7c98dfd4df1ab50026c149f21fb719fc6a2a09d040a9db4df647f132bc"
P5_MANIFEST_SHA256 = "02d857f555623c10dc44998cd202c2da6226ec5c40a94a75020d75df87f02518"


def sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def git_output(directory: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(directory), *args],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--replay-log", type=Path, required=True)
    parser.add_argument("--replay-exit-code", type=int, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--px4-dir", type=Path, required=True)
    parser.add_argument("--build-provenance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    replay_log = args.replay_log.read_text(encoding="utf-8", errors="replace")
    provenance: dict[str, Any] = json.loads(
        args.build_provenance.read_text(encoding="utf-8")
    )
    tracked_status = git_output(ROOT, "status", "--porcelain=v1", "--untracked-files=no")
    px4_commit = git_output(args.px4_dir, "rev-parse", "HEAD")
    library_root = ROOT / "ros2_ws/src/px4_ros2_interface_lib"
    library_commit = git_output(library_root, "rev-parse", "HEAD")
    executable_sha256 = sha256(args.executable)
    library_sha256 = sha256(args.library)
    px4_sha256 = sha256(args.px4_dir / "build/px4_sitl_default/bin/px4")
    expected_rejection = (
        args.replay_exit_code == 42
        and EXPECTED_EXCEPTION in replay_log
        and '"event_type":"mode_executor_registered"' not in replay_log
    )
    checks = {
        "expected_constructor_exception": expected_rejection,
        "registration_not_reached": '"event_type":"mode_executor_registered"' not in replay_log,
        "exact_current_library_commit": library_commit
        == "c3e410f035806e8c56246708432ded09c976434b",
        "exact_current_library_binary": library_sha256
        == "dddfa0698c27617ce5a368dc7d0d5272bc510f3cb780c5ef3f48c77d098380e6",
        "exact_px4_commit": px4_commit
        == "4ae21a5e569d3d89c2f6366688cbacb3e93437c9",
        "exact_px4_binary": px4_sha256
        == "931320a07585dabf36ca9c8ba994756b93ee7d154cd9c8930b2171548d978993",
        "executable_matches_build_provenance": executable_sha256
        == provenance.get("adapter_binary_sha256"),
        "source_matches_build_provenance": sha256(
            ROOT / "scripts/adapters/external_mode_adapter/src/issue162_replay.cpp"
        )
        == provenance.get("adapter_source_sha256"),
        "tracked_worktree_clean": tracked_status == "",
        "p5_v6_gate_unchanged": sha256(P5_GATE) == P5_GATE_SHA256,
        "p5_v6_manifest_unchanged": sha256(P5_MANIFEST) == P5_MANIFEST_SHA256,
    }
    accepted = all(checks.values())
    result = {
        "schema_version": "1.0",
        "study_id": "external_rtl_successor_issue_162",
        "attempt_kind": "current_locked_constructor_and_registration_replay",
        "run_id": args.run_id,
        "status": "NOT_REPRODUCED_ON_CURRENT" if accepted else "REJECTED",
        "classification": (
            "UNSUPPORTED_COMBINATION_REJECTED" if accepted else "EVIDENCE_FAILURE"
        ),
        "reason": (
            "current library rejected executor-owned internal RTL replacement before registration"
            if accepted
            else "current replay did not satisfy its preregistered identity and rejection checks"
        ),
        "acceptance_checks": checks,
        "lifecycle_applicability": "NOT_APPLICABLE" if accepted else "UNKNOWN",
        "runtime": {
            "replay_exit_code": args.replay_exit_code,
            "registration_reached": '"event_type":"mode_executor_registered"' in replay_log,
            "expected_exception_observed": EXPECTED_EXCEPTION in replay_log,
        },
        "identity": {
            "repository_commit": git_output(ROOT, "rev-parse", "HEAD"),
            "tracked_worktree_status": tracked_status.splitlines(),
            "px4_commit": px4_commit,
            "px4_binary_sha256": px4_sha256,
            "px4_ros2_interface_lib_commit": library_commit,
            "px4_ros2_interface_lib_binary_sha256": library_sha256,
            "executable_sha256": executable_sha256,
            "source_sha256": sha256(
                ROOT / "scripts/adapters/external_mode_adapter/src/issue162_replay.cpp"
            ),
            "preregistration_sha256": sha256(
                ROOT
                / "experiments/motivation/successor/primary_reproduction_preregistration.yaml"
            ),
            "build_provenance_sha256": sha256(args.build_provenance),
        },
        "artifact_sha256": {"replay_log": sha256(args.replay_log)},
        "p5_v6_isolation": {
            "status": (
                "PASS"
                if checks["p5_v6_gate_unchanged"]
                and checks["p5_v6_manifest_unchanged"]
                else "FAIL"
            ),
            "protected_hashes": {
                "p5_v6_differential_gate": sha256(P5_GATE),
                "p5_v6_manifest": sha256(P5_MANIFEST),
            },
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": result["status"], "output": str(args.output)}))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
