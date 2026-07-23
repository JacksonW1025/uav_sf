# V0-P qualification runbook independent re-review

Date: 2026-07-23

Decision: `DECLINE_IMPLEMENTATION_NOT_READY`

Status: `QUALIFICATION_NOT_AUTHORIZED`

## Review boundary

The review used file inspection, independent hashes, schema validation,
focused fixtures, runner `plan`, runner `preflight`, refusal paths, dependency
identity checks, a registry digest lookup, `ros2 --help`, and read-only
process/port checks. It did not launch PX4, Gazebo, ROS, DDS flight
communication, a flight scenario, a recorder, a qualification attempt, or a
comparison arm.

The original review and its 11 blockers remain historical facts. The readiness
amendment's 11 resolution claims were re-tested from source and were not
treated as approval.

## Confirmed contracts

- All 15 frozen bundle hashes match the original review source lock.
- The seed catalog remains 61 rows: 50 accepted current runtime seeds, one
  historical replay, 10 excluded rows, and zero unresolved rows.
- The qualification map contains exactly six fixed current Family A runtime
  seeds and excludes historical replay, R1, W1, Family B, direct actuator, and
  validation-only rows.
- Route Oracle 0.4, Freshness Oracle 0.1, Successor Oracle 0.1, Linearization
  Oracle 0.2, their schemas, and the frozen thresholds retain exact identity.
- The target remains three accepted attempts and the maximum remains six
  formal attempts. Comparison accounting remains separate and non-transferable.
- Static `plan` and `preflight` return static PASS, while the current DECLINE,
  comparison strategies, historical replay, unmapped seeds, attempt seven, and
  a non-V0-P phase are refused before runtime.
- Fixture-level evidence, safety, cleanup, residual-process, stale-state,
  artifact-closure, terminal-state, and UDP/TCP 8888 checks preserve their
  non-collapsing outcomes.

## Blocking findings

`E-11` — The runner requires `APPROVE_QUALIFICATION` with
`AUTHORIZED_NOT_STARTED`, not the only permitted new approval contract
`APPROVE_QUALIFICATION_ONLY` with
`QUALIFICATION_AUTHORIZED_NOT_STARTED`. It also compares the current decision
file hash with the first decision commit, so the required later identity-lock
edit would invalidate that comparison.

`E-12` — The runner accepts a local commit resolved by `git rev-parse` and an
arbitrary ledger path. It does not require the decision and ledger to match
the exact pushed `origin/main` identity or the authorization fields inside the
new bundle.

`F-07` — The manifest declares per-slot collector and Oracle bundles, but the
scenario entries do not invoke those bundles. In particular, the P0 executor
path does not invoke the Successor Oracle, P2/P3 do not invoke the Freshness
Oracle, and C1 does not invoke the Route or Successor Oracles.

`F-08` — No mapped scenario entry produces `safety_evidence.json`,
`cleanup_evidence.json`, or `compact_evidence.json`. The runner checks for
these files only after the scenario returns, so every otherwise successful
scenario reaches an execution failure rather than an admissible evidence
classification.

`H-16` — The safety checker runs after the scenario subprocess completes. It
can classify a fixture or completed record, but it cannot observe and stop the
active bounded SITL qualification when a finite-value, physical-boundary,
ground-contact, PX4-abort, clock-stall, or timeout condition occurs.

`J-12` — The environment lock contains a base-image digest, not a digest for
the complete qualification image. ROS, Gazebo, and most Python packages are
installed from non-snapshotted sources, so the complete reproducible
environment identity is not frozen.

`J-13` — The base digest resolves and includes arm64, but the selected ROS
Jazzy environment could not be executed or checked for required imports. The
available host is ROS Humble, and `px4_ros2_interface_lib` is not importable
there. The amendment checker only parses files and shell syntax; it does not
run the selected `ros2` or import checks.

`J-14` — The C1 slot does not override the scenario entry's ignored
Humble-built DDS Agent and C1 adapter defaults. Those binaries are not in the
manifest, and the Jazzy workspace has no C1 executable. The P2/P3
instrumented runtime binary identity is likewise not bound by the manifest's
source-only records.

`K-09` — The runner launches the scenario before any append-only ledger
registration and contains no path that records accepted or rejected attempt
closure. This cannot preserve the frozen rule that every launched formal
attempt consumes the maximum of six.

## Decision and next action

Qualification runtime, Official Sequence, Bounded Random Timing Comparator,
State-Aware Mutation, historical replay runtime, real workload, Family B,
direct actuator, HITL, and real flight remain unauthorized. Static checks did
not create `V0P-A1`; the ledger remains empty.

Next exact action:

> create an independent blocker-resolution amendment for the new review findings
