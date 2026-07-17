# Phase A.2 Route Transition Measurement Report

## Repository boundary

- Starting commit: `a028b2e6c3a2b34f7364483a192c44b8ac4777e1`.
- Locked PX4 commit: `4ae21a5e569d3d89c2f6366688cbacb3e93437c9`.
- Locked `px4_msgs`: `18ecff03041c6f8d8a0012fbc63af0b23dd60af1`.
- Locked `px4_ros2_interface_lib`: `c3e410f035806e8c56246708432ded09c976434b`.
- Final implementation commit: recorded in the terminal handoff after the
  validated content is committed; a commit cannot embed its own hash.

Only `main` was used. Raw runs and failed attempts remain ignored under
`runs/phase_a2/`, `runs/p0*`, `runs/p2/`, and `runs/p3/`.

## Queue study and sequence-gap root cause

The 15-run [queue study](../design/ROUTE_OBSERVABILITY_QUEUE_STUDY.md) varied
only `ORB_QUEUE_LENGTH` across 1, 4, 8, 16, and 32, with three matched hover
runs per queue. q1 lost 13–19 publisher-local sequence values despite zero
ULog write dropouts. Every q4/q8/q16/q32 repeat retained 100% of the publisher
sequence range and had zero target critical-window gaps.

This isolates the original 16 ms holes to overwrite of the default one-message
uORB buffer before the logger subscriber read it, not logger storage loss.
q4 is the smallest passing queue and is the canonical patch value. The q4
patch applies to a fresh locked worktree and builds `px4_sitl_default`.

## Global and critical capture quality

Measurement quality is split into global and transition-local layers. The
accepted P0, P2, and P3 source-to-fallback target windows have no publisher
sequence gaps and instrument all locked multicopter final-writer candidates
(`control_allocator`). Global accepted captures are `COMPLETE`. Startup,
inactive, or explicit-cleanup windows can be `BOUNDED`; Oracle 0.2 uses the
tested transition's local window and returns `UNKNOWN` below its measured
resolution rather than globally promoting or rejecting a flight.

## Route epoch and identities

The [epoch model](../design/ROUTE_EPOCH_MODEL.md) defines boot-local monotonic
`route_epoch_id`, External `route_activation_id`, Offboard
`producer_session_id`, and External `registration_instance_id`. The
observation-only PX4 patch emits the epoch after final route selection and
carries it through setpoint-consumption, allocator, writer, lifecycle, and
arming observations. Collector precedence puts an epoch change before a
same-timestamp data event. Shared writer names no longer imply shared route
ownership.

## Clock bridge

The implemented [affine bridge](../design/CLOCK_BRIDGE_IMPLEMENTATION.md) fits
PX4 boot microseconds to ROS nanoseconds from same-callback `TimesyncStatus`
samples, detects resets/jumps, and reports a segment ID, validity interval,
rate, residuals, and uncertainty. Thresholds were fixed before controlled P0,
D, P2, and P3 execution: at least 20 samples, 100 ms VALID residual, 250 ms
DEGRADED residual, 20 ms maximum DDS round trip, and 50 ms segment jump.

All accepted P0, P2, and P3 bridges are `VALID`. P2 uncertainty is
27.8–96.0 ms; P3 uncertainty is 29.1–94.8 ms. DEGRADED or insufficient-sample
runs were excluded without threshold changes and retain `UNKNOWN` cross-domain
results.

## Registry removal and arming-denial observation

PX4 observations now distinguish unregister processing, mode/executor/arming
slot removal, registration results, and arm-request rejection. Each event
includes result/reason, registration IDs, active-at-removal, fallback, and
epoch context.

The first D0 diagnostic showed that manual Position mode requires manual
control in this no-RC setup. Locked source and command acknowledgements
identified this as an internal experiment precondition, not External residue.
The accepted D0 used valid Internal Hold (`AUTO_LOITER`) and did not relax an
arming check. The final path had valid position/land state and accepted arm
commands.

## P0-D results and Re-entry Gate

- [P0-D0](../motivation/P0D0_INTERNAL_REARM_REPORT.md): PASS; internal RTL
  auto-disarm to successful rearm in 5.200 s, without an External process.
- [P0-D1](../motivation/P0D1_REGISTRATION_REENTRY_REPORT.md): PASS; two fresh
  registrations, two processed unregisters, all applicable slots removed, and
  no stale active registration.
- [P0-D2](../motivation/P0D2_FULL_REENTRY_REPORT.md): PASS with conclusion
  `clean_reentry`; no old-epoch data-plane events after removal and no
  automatic External reactivation.

The [Re-entry Gate](../../experiments/motivation/phase_a2_reentry_gate.json) is
PASS for R1–R3.

## Schema 1.2 and Route Oracle 0.2

Route traces validate as schema 1.2 with the five new epoch/identity/source
fields. The 1.1 migrator writes `null` for identities it cannot infer and marks
all retained Phase A.1 summaries as superseded; it never fabricates epochs.

[Route Oracle 0.2](../design/ROUTE_ORACLE_V0.md) evaluates revocation,
installation, exclusivity, continuity, and recovery with source/target epochs,
old-epoch post-revocation counts, local capture quality, and the affine clock
bridge. P0 and P2 have all five clauses PASS. P3 retains `UNKNOWN` for ten
bounded cleanup clauses and reports no violation.

## P0-A/B/C Phase A.2

The [Phase A.2 baseline report](../motivation/P0_PHASE_A2_BASELINE_REPORT.md)
contains exactly three accepted Offboard, Dynamic External, and Mode Executor
runs. All nine have execution PASS, route verdict PASS, VALID clock bridges,
COMPLETE target critical windows, usable epoch/producer identities, and five
PASS Oracle clauses.

The [Measurement Gate](../../experiments/motivation/phase_a2_measurement_gate.json)
is PASS for M1–M11 and was frozen before P2 began.

## P2 process loss

The [P2 report](../motivation/P2_PROCESS_LOSS_REPORT.md) and
[18-row matrix](../../experiments/probes/p2/experiment_matrix.tsv) cover
Offboard and Dynamic External Mode under SIGTERM, SIGKILL, and a fixed
SIGSTOP/SIGCONT pause, three accepted repeats each. All 18 behavior verdicts,
bridges, and Oracle results are PASS. Detection spans 47–252 ms for graceful
shutdown and 1.05–1.40 s for crash/pause loss. Maximum altitude loss is
0.153 m, and no accepted case has post-revocation old-epoch consumption or
writer output.

## P3 channel decoupling

The [P3 report](../motivation/P3_HEARTBEAT_SETPOINT_DECOUPLING_REPORT.md) and
[24-row matrix](../../experiments/probes/p3/experiment_matrix.tsv) cover all
four proof-of-life/health and setpoint combinations, three repeats per object.
All 24 channel-behavior verdicts and bridges are PASS/VALID. Proof-of-life or
health ON retains the route regardless of setpoint state; OFF triggers fallback
regardless of continued setpoints. Nineteen overall Oracle results are PASS and
five are UNKNOWN because explicit cleanup windows are locally bounded; none is
a violation.

P3 never kills the process to create a channel combination. Process shutdown
starts after the fixed channel window closes.

## Tests and CI

The final local validator covers Python syntax, shell syntax, dependency locks,
JSON/YAML/TSV parsing, Markdown links, patch scope/applicability, queue rules,
epoch ordering, schema 1.2, clock schema/segmentation, lifecycle logic, D gates,
Oracle 0.2, accepted P2/P3 matrix cardinality, ignored/raw boundaries, and the
10 MiB limit. The locked fresh-worktree observation-patch rebuild also passes.

GitHub CI explicitly runs the Phase A.2 patch, queue, epoch, clock, interface,
lifecycle, gate, matrix, trace-schema, and Oracle tests before the full
repository validator. GitHub-hosted CI does not run PX4/SITL.

## Final repository state

At handoff, the final checks require a clean worktree, zero unpushed and
unpulled commits, zero unexpected untracked or tracked-ignored files, zero
tracked `runs/` files, and zero tracked files over 10 MiB. Exact final commit
and ahead/behind counts are reported by the terminal handoff after push.

## Remaining research limitations

- The locked DDS configuration does not publish
  `/fmu/out/vehicle_angular_velocity`; angular-rate peak is explicitly
  `UNKNOWN`, while attitude and altitude remain measured.
- Individual Dynamic External arming-check reply timestamps are not logged by
  the locked interface, so exact last health-reply time is `UNKNOWN`; setpoint,
  fault, PX4 consumption, and fallback times remain bounded.
- SITL/Gazebo intermittently aborted with a glibc mutex/stack assertion.
  A watchdog preserves and excludes these environment failures; accepted
  matrices contain only complete, clock-valid results.
- Three repeats per deterministic configuration do not estimate probability
  and do not constitute fuzzing, P5, or full external-framework integration.
