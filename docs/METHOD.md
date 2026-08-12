# Method

## Controlled generation

Each new experiment chooses one of three strategies under the same plan,
safety limits, evidence rules, and Oracle configuration:

- **Official sequence** executes the specified action order without timing
  mutation.
- **Bounded random timing** samples only preregistered timing intervals with a
  recorded deterministic seed.
- **State-aware strategy** selects an enabled action using uncovered contract
  boundaries, route state, lifecycle state, and distance to a configured
  deadline. It cannot bypass action preconditions or safety rules.

## Collection

Adapters normalize source observations into the event schema. The collector
assigns a contiguous sequence and a SHA-256 hash chain. Critical route events
retain the source time domain and clock-bridge identity. Collection is bounded
by explicit start and stop events. Runtime files are written below `runs/`.
The trace also carries a target-environment attestation copied from the
preregistered plan; validation performed on a repository maintenance host is
not a substitute for this runtime observation.

## Evidence Admissibility Gate

The gate rejects a trace as inadmissible when it has an invalid hash chain,
noncontiguous sequence, inconsistent run identity, missing collection bounds,
missing plan-required event kinds, a critical collection gap, an unmapped time
domain, or incomplete route identity on an authority-bearing event. An
environment attestation that is missing, misplaced, duplicated, or different
from the plan also makes the trace inadmissible. An inadmissible trace produces
an overall `INCONCLUSIVE` result even if an individual clause appears
favorable.

## Contracts

The Route Conformance Oracle checks source revocation, target installation,
exclusive writers, and actuator-effect continuity. The Freshness and Lineage
Oracle checks consumed command age and end-to-end identity across the complete
target-authority window, so a setpoint-only stall remains visible even when
proof-of-life continues. The Successor Progression Oracle independently checks
completion successor installation, explicit fault observation, and complete
safety-route installation only when a fallback is preregistered. The
Registration Contract Oracle checks explicit registration and activation
rejections; lack of activation alone is never accepted as rejection evidence.

Clause states are `PASS`, `VIOLATION`, `UNKNOWN`, and `NOT_APPLICABLE`. Overall
`PASS` requires an admissible trace and every applicable clause to pass.

## Safety and cleanup

The supervisor stops a run on heartbeat loss, collector loss, clock failure,
non-finite control values, physical boundary violation, or timeout. The
cleanup checker requires a closed collector, no active external registration
or producer session, a safe internal route, landing when required, and
disarming. A flight attempt is not closed in accounting until cleanup passes.
