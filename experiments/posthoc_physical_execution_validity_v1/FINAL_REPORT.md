# Post-hoc Physical Execution Validity v1

## Scope and paper role

This is a read-only audit of all 151 frozen admissible Thor Motivation traces:
131 primary and 20 supplemental. It belongs to the paper's Motivation Study
and threats-to-validity discussion. It does not modify a Stage A1 plan, trace,
evaluation, threshold, ledger, denominator, summary, or report. The frozen
formal result remains 94 `PASS` and 57 `VIOLATION`.

The audit answers a narrower question that the Stage A1 Evidence Gate did not
ask: did the vehicle reach a physically meaningful airborne state, and what
continuous motion is visible in host-monotonic windows aligned with the
registered transition evidence? These measurements are descriptive. They are
not a fifth Oracle and do not replace route correctness.

## Frozen rule and separation

The analysis plan defines physical execution as a maximum height of at least
0.5 m above the PX4 local NED origin. This reuses the existing active safety
supervisor's altitude condition for `became_airborne` and does not rely on one
`landed == false` sample.

The corpus has a clear separation around this rule:

- 12 traces reached at most 0.079787463 m;
- the next-lowest trace reached 1.801775932 m;
- 139 traces therefore form the airborne descriptive stratum and 12 form the
  non-airborne stratum;
- any cutoff greater than 0.079787463 m and no greater than 1.801775932 m
  produces the same split.

The split is post-hoc and never replaces the preregistered Stage A1 Evidence
Gate. It instead defines which frozen traces may enter physical-effect
summaries and what Stage A2 must reject prospectively.

## Non-airborne attempts

| Attempt | Cell | Maximum height | Frozen result | Frozen violation clauses |
| --- | --- | ---: | --- | --- |
| `det-offboard-attitude-land-002` | `det-offboard-attitude-land` | 0.003570 m | VIOLATION | installation |
| `det-offboard-attitude-land-004` | `det-offboard-attitude-land` | 0.049061 m | VIOLATION | continuity |
| `det-offboard-body-rate-land-002` | `det-offboard-body-rate-land` | 0.031576 m | PASS | none |
| `det-offboard-body-rate-land-004` | `det-offboard-body-rate-land` | 0.079787 m | PASS | none |
| `det-offboard-body-rate-land-005` | `det-offboard-body-rate-land` | 0.007874 m | PASS | none |
| `fault-offboard-attitude-stall-003` | `fault-offboard-attitude-stall` | 0.037275 m | VIOLATION | continuity, freshness |
| `fault-offboard-attitude-stall-005` | `fault-offboard-attitude-stall` | 0.036729 m | VIOLATION | installation |
| `fault-offboard-body-rate-stall-001` | `fault-offboard-body-rate-stall` | 0.061864 m | VIOLATION | freshness |
| `fault-offboard-body-rate-stall-003` | `fault-offboard-body-rate-stall` | 0.066257 m | VIOLATION | freshness |
| `fault-offboard-body-rate-stall-004` | `fault-offboard-body-rate-stall` | 0.066351 m | VIOLATION | freshness |
| `fault-offboard-body-rate-stall-005` | `fault-offboard-body-rate-stall` | 0.056526 m | VIOLATION | freshness |
| `fault-offboard-body-rate-stall-008` | `fault-offboard-body-rate-stall` | 0.017147 m | VIOLATION | freshness |

Three of the 12 traces are frozen `PASS` results and nine are frozen
`VIOLATION` results. The latter contain ten violation clauses: six freshness,
two installation, and two continuity clauses. Those route-level observations
remain part of Stage A1 under its registered plan, but the traces do not enter
the physical-effect distributions in this analysis.

## Aligned physical windows

Telemetry `received_monotonic_ns` is aligned directly with the normalized
trace's `analysis_monotonic` timestamps. The analysis records five window
types for each of 163 registered transition instances:

- target request through installation;
- target activation through revocation;
- first effect exceeding the frozen command-age bound through authority end;
- registered fault through successor/fallback or authority end;
- completion/fault anchor through complete successor/fallback installation.

All 163 transition-installation and target-authority windows have calculable
telemetry; 151 of each belong to airborne traces. Forty-eight freshness
exposure windows are observed, of which 41 belong to airborne traces. The
airborne freshness windows comprise 32 trajectory, six attitude, and three
body-rate instances.

For the six airborne attitude freshness windows, maximum displacement from the
window start has median 0.049972 m and maximum 0.152084 m. For the three
airborne body-rate windows, the corresponding median is 0.107415 m and maximum
is 0.115381 m. These are bounded descriptive signatures, not causal estimates
or evidence of a public PX4 requirement violation.

Trajectory freshness has a different interpretation. The Stage A1 fixtures
publish a constant position and leave velocity and acceleration unset. A stale
trajectory target is therefore numerically identical to a fresh target. Motion
seen later in a process-exit/fallback window can include recovery and landing;
it does not identify the consequence of numerical setpoint staleness. The
proper conclusion is `STRUCTURALLY_MASKED`, not "no physical consequence."
Stage A2 must use a time-varying position target to remove this ambiguity.

## Validity finding and next gate

The current Offboard fixture sets its historical `ever_airborne` flag after a
single `VehicleLandDetected.landed == false` sample. The 12-trace stratum shows
that this event is insufficient to establish physical execution. A future
formal moving-workload plan must require, before injection or completion:

- valid local-position evidence;
- a registered minimum height held for a registered dwell;
- a multi-signal airborne predicate rather than a one-sample latch;
- entry into the registered motion phase and minimum path progress.

Failure of those prospective conditions must make the attempt inadmissible or
otherwise explicitly invalid for the registered study. It must not be
interpreted as an Oracle pass or violation.

## Interpretation boundary

This audit establishes a construct-validity limitation and a prospective Gate
requirement. It does not establish that the 12 traces are corrupt, erase their
route observations, recalculate the Stage A1 denominator, prove a PX4 defect,
or demonstrate real-flight consequences. Continuous effects are calculated
only for the airborne descriptive stratum, and unresolved causal attribution
is carried into the separate finding/consequence triage.

`input-manifest.json` records the digest of every plan, closed trace, frozen
evaluation, and raw telemetry sidecar, plus the frozen matrices, ledgers, and
analysis plan. The following command reproduces the generated JSON artifacts
without writing to any frozen input:

```sh
python3 -m scripts.analysis.physical_execution \
  --root . \
  --analysis-plan experiments/posthoc_physical_execution_validity_v1/analysis-plan.json \
  --output-root /tmp/posthoc-physical-execution-validity-v1
```
