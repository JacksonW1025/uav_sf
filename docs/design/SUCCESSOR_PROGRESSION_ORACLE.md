# Successor Progression Oracle

Version: `0.1`. Result schema: `1.0`. Lifecycle event schema: `1.0`.

## Purpose

The Successor Progression Oracle is independent of Route Oracle 0.4. It checks
whether an external-mode lifecycle advances from ownership through completion
to the expected successor and terminal mission state. Route Oracle remains the
authority for source revocation, target installation, writer exclusivity, and
continuity; this oracle consumes its result rather than changing its rules.

```text
LifecycleProfile
  vs
Observed ownership → completion → request → installation → terminal state
```

Missing lifecycle, clock, route, or terminal evidence is `UNKNOWN`, never
`PASS`.

## Inputs

- `successor_lifecycle_event.schema.json`: ROS-side observations of successful
  registration, `VehicleStatus.executor_in_charge`, `ModeCompleted`, Mode
  Executor commands, LandDetected, arming state, and clock samples;
- the structured external-mode/executor log, which proves completion generation,
  receipt callback, successor state-machine transition, and deactivation;
- the canonical route trace, which supplies the target route epoch without
  extending the stable Route Oracle schema;
- a selected External→Land Route Oracle 0.4 result;
- a preregistered lifecycle profile with owners, successor, deadlines, and
  terminal condition.

Cross-domain route timing still requires a `VALID` clock bridge. Lifecycle
request/selection deadlines use receive timestamps from the same monitor clock;
they are not calculated by subtracting ROS time from PX4 boot time.

## Clauses

### Ownership

When the registered owned external mode is active, the registered executor ID
must equal `VehicleStatus.executor_in_charge`. A proved mismatch is
`EXECUTOR_NOT_IN_CHARGE`; missing registration or status evidence is `UNKNOWN`.

### Completion

The completion condition must generate `external_mode_completed`, PX4 must
publish a successful matching `ModeCompleted`, and the owning executor must log
the matching successful receiver callback. Generated-but-undelivered completion
is `COMPLETION_NOT_DELIVERED`.

### Successor request

After completion delivery, the expected Mode Executor command must be observed
within the profile deadline. A complete monitor window without it is
`EXPECTED_SUCCESSOR_NOT_REQUESTED`.

### Successor installation

Commander must select the expected Land nav state within its deadline, and the
selected External→Land Route Oracle result must report installation `PASS` on a
distinct route epoch. Absence, wrong selection, or failed installation maps to
the corresponding successor category. Route `UNKNOWN` remains lifecycle
`UNKNOWN`.

### Mission progression

The external mode must deactivate, Land must be reached, and the vehicle must
disarm within the terminal deadline. Complete evidence without those states is
a violation; incomplete evidence is `UNKNOWN`.

## Overall result

- any applicable clause `VIOLATION` → `VIOLATION`;
- all applicable clauses `PASS` → `PASS`;
- an explicitly unsupported profile → `NOT_APPLICABLE`;
- otherwise → `UNKNOWN`.

The executable is `scripts/oracles/successor_progression_oracle.py`. The normal
baseline profile is
`experiments/motivation/successor/baseline_lifecycle_profile.yaml`.
