# Family A Fuzzer v0 qualification activation review

Date: 2026-07-22

Decision: `DECLINE_IMPLEMENTATION_NOT_READY`

Status: `QUALIFICATION_NOT_AUTHORIZED`

## Review boundary

This review used only static inspection, parsing, schema validation, unit
tests, source and hash verification, dependency identity checks, and
non-runtime command-interface help. It did not start PX4, Gazebo, ROS, DDS, a
simulator, an adapter, or any flight process. It created no `V0P-A1` attempt.

The reviewed preregistration commit and starting repository identity are both
`426f4c7316e973c6a4dab84a202fdb75ea65b7c1`. The original activation Gate
continues to state `PREREGISTERED_NOT_ACTIVATED`; it remains frozen evidence
that the preregistration never activated itself.

## Source, seed, and scope findings

All 15 frozen bundle hashes match the
[review source lock](../../experiments/fuzzer_v0/family_a/activation_review/review_source_lock.yaml).
The required source commits resolve and are ancestors of the reviewed
repository history.

The seed catalog contains 61 records: 50 current accepted Family A runtime
seeds, one historical Issue 162 replay benchmark, 10 excluded records, and no
unresolved record. No validation-only record enters the runtime pool. R1
session rollover, W1 real-workload runtime, B1 and Family B, direct actuator,
HITL, and real flight remain outside the runtime scope.

## Oracle and evidence findings

Route Oracle 0.4, Freshness Oracle 0.1, Successor Progression Oracle 0.1,
Authority Event Linearization Oracle 0.2, Evidence Admissibility Gate 1.0, and
all associated executable, schema, profile, and clock identities match their
frozen hashes.

The `route-oracle-v0.3-default` profile string is retained explicitly as the
Route Oracle 0.4 threshold-profile name. It is not a Route Oracle 0.3
executable or result identity. The formal bundle sets
`old_Route_Oracle_0_3_identity_used=false`.

## Qualification contract findings

The frozen contract defines V0-P as a qualification phase with a target of
three accepted attempts and a maximum of six formal attempts. Qualification is
outside the 36-attempt comparison budget, cannot transfer budget, and cannot
produce a strategy-superiority claim. All comparison arms remain locked.

The activation review defines a fixed six-slot canonical seed schedule for a
future readiness-resolved runner. It does not change any frozen seed, state,
Oracle threshold, budget, event grammar, mutation grammar, or variation
domain.

## Blocking implementation and environment findings

Eleven blocking clauses failed:

1. no unique V0-P qualification runner exists;
2. no executable mapping binds frozen seed rows to qualification scenarios;
3. the existing collectors are not bound to a qualification attempt path;
4. no qualification compact-evidence generator exists;
5. no qualification cleanup-audit checker exists;
6. no machine-enforced V0-P-only mode excludes all comparison strategies;
7. no unified qualification safety-monitor entry exists;
8. finite-value and physical bounds are not integrated into a V0-P path;
9. no residual-process post-attempt checker exists;
10. no common occupied-port preflight and post-attempt checker exists; and
11. the locked ROS Jazzy setup is unavailable.

The existing `scripts/fuzzer` executor is explicitly pre-M-FINAL prototype
material. It reads the old seed manifest, emits Route Oracle 0.3 result
identity, and cannot satisfy the frozen evidence classifications or
qualification ledger. Existing P0/P2/P3/P5 scripts and individual collectors
and Oracles demonstrate reusable components, but they do not form a unique,
non-comparison V0-P command path.

## Decision

The decision is `DECLINE_IMPLEMENTATION_NOT_READY`. Qualification, runtime,
Official Sequence, Bounded Random Timing, State-Aware Mutation, historical
replay runtime, real workload, Family B, direct actuator, HITL, and real flight
are all unauthorized. The qualification ledger is `NOT_AUTHORIZED`, contains
zero formal and zero accepted attempts, and has an empty attempt list.

The recorded gaps can be resolved without changing the frozen research design,
but they require an independent readiness-resolution plan and a later static
activation review. This review cannot repair the gaps and automatically turn
the decision into approval.

Next exact action:

> create an independent amendment or readiness-resolution plan for the recorded blockers
