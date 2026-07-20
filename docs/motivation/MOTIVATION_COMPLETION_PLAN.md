# Motivation Completion Plan

Date: 2026-07-20

Study boundary: bounded, defensive PX4/Gazebo SITL research on flight-safety,
software-reliability, and runtime-consistency properties. The workflow uses
only locally owned processes, public flight-control interfaces, observation-only
instrumentation, and the repository's existing evidence facilities.

## Shared execution rules

Every phase freezes exact source and binary identity, acceptance criteria,
target windows, lineage requirements, safety bounds, attempt caps, and cleanup
before formal execution. Cross-domain claims require a `VALID` clock bridge.
Incomplete observability is never promoted to PASS or VIOLATION. A controlled
failure condition, locally owned process termination, setpoint publication
pause, health-channel continuation, lifecycle timing variation, or
message-delivery delay in the local SITL namespace is recorded with its exact
public-interface semantics.

At each phase boundary:

1. update this plan and `docs/repository/MOTIVATION_COMPLETION_STATE.md`;
2. run focused tests;
3. run `./scripts/validation/validate_repo.sh`;
4. commit only the phase's scoped records and implementation;
5. push to `origin/main`;
6. confirm `HEAD == origin/main`, ahead/behind `0/0`, and a clean worktree.

Any unexpected early ground contact, simulator-clock stall, PX4 abort,
out-of-bound control value, incomplete critical window, invalid clock bridge,
or unsafe cleanup ends that attempt. Raw evidence is preserved in ignored
storage and excluded from the SUT denominator under the correct classification.

## Execution order

### N1 — Current natural event adjudication

Status: `COMPLETE` — `CURRENT_EVENT_REOBSERVED_BUT_PHASE_DEPENDENT`. The formal
matrix closed at 8 accepted / 14 attempts because A reached its cap at 2/3;
B and C reached 3/3. C04 and C05 reproduced the stale-subject-only Route
violation. The required reduced run was accepted Route PASS on its first
attempt, so unused reduced seeds were not run. Source audit supports a retained
Trajectory-input candidate, but no stable rate, proven root cause, old external
allocator/writer lineage, or physical consequence is claimed.

Outputs:

- `experiments/motivation/n1_trajectory_residue/preregistration.yaml`
- `experiments/motivation/n1_trajectory_residue/matrix.yaml`
- `experiments/motivation/n1_trajectory_residue/attempt_ledger.yaml`
- `data/processed/motivation/n1_trajectory_residue/`
- `docs/motivation/N1_TRAJECTORY_RESIDUE_REPORT.md`

Execute phase buckets A/B/C with three accepted runs each, at most six
attempts per bucket and eighteen total. Preserve the F1 vehicle, Trajectory
velocity, controlled process-stop condition, fallback, stability/physical
thresholds, PX4/interface revisions, and Route Oracle 0.4. Derive each bucket
through legal harness waiting/start timing, never by direct PX4 health-state
mutation.

Stop when all nine accepted runs exist or the relevant attempt cap is reached.
If at least two accepted runs reproduce the same violation, run at most three
observation-reduced attempts for one accepted confirmation, then produce a
minimal testcase and source-level candidate explanation. Otherwise report the
bounded non-reproduction without erasing the original found event.

### C1 — Concurrent authority-event deterministic probe

Status: `PREREGISTERED`; commit `2cb2e021f1604868387f94b5eef6b6457f719416`
was pushed before any formal attempt. The public-interface harness, Authority
Event Linearization Oracle 0.1, 15-slot matrix, two-attempt slot caps, and
three-attempt triggered-confirmation cap are frozen.

Outputs:

- `docs/design/AUTHORITY_EVENT_LINEARIZATION_ORACLE.md`
- `scripts/oracles/authority_event_linearization_oracle.py`
- `data/schemas/authority_event_linearization_result.schema.json`
- `experiments/motivation/c1_concurrency/`
- `docs/motivation/C1_CONCURRENT_AUTHORITY_EVENTS_REPORT.md`
- `experiments/motivation/c1_concurrency/c1_gate.json`

Cover event pairs C1-A through C1-E under A-first, near-simultaneous, and
B-first orders. The target is fifteen accepted slots, each capped at two
attempts, with thirty attempts total. Events use only public command and SITL
control interfaces. The Oracle accepts only a unique, explainable authority
owner and a final route equivalent to a legal serial order, with complete
lineage, no illegal writer overlap or route gap, and Land/Disarm cleanup.

Stop at slot/total caps. A found violation permits no more than three minimal
confirmation attempts in this phase and does not authorize a timing sweep.

### R1 — Rapid re-entry and session rollover

Status: `NOT_STARTED`.

Outputs:

- `docs/design/SESSION_ROLLOVER_ORACLE.md`
- `scripts/oracles/session_rollover_oracle.py`
- `experiments/motivation/r1_session/`
- `docs/motivation/R1_SESSION_ROLLOVER_REPORT.md`
- `experiments/motivation/r1_session/r1_gate.json`

Run clean re-entry, local process restart, and one source-audited delayed
old-session message semantic. The last case uses a bounded message-delivery
delay in the local SITL namespace with explicit old/new identity and no
third-party endpoint. Target three accepted runs per scenario, maximum six
attempts per scenario.

Stop at nine accepted runs or a scenario's cap. Do not add more delayed message
types during this phase; record non-selected types only in a future matrix.

### W1 — Real-workload runtime/trace spike

Status: `NOT_STARTED`.

Outputs:

- exact source/build and trace records under
  `experiments/motivation/w1_workload/`
- `docs/motivation/W1_REAL_WORKLOAD_SPIKE_REPORT.md`
- `experiments/motivation/w1_workload/w1_gate.json`

Audit Aerostack2 first and MRS UAV System ROS 2 only as the bounded fallback.
Extract at least one replayable lifecycle/mode/setpoint trace, then run at least
three accepted Canonical Adapter replays. Run no more than three native-adapter
spikes only if source audit proves new route/lifecycle semantics and bounded
integration cost.

Stop with one of the preregistered workload dispositions; do not perform a
large integration or refactor solely for realism.

### B1 — Registered-controller inventory and Family B Gate

Status: `NOT_STARTED`.

Outputs:

- `docs/motivation/B1_REGISTERED_CONTROLLER_INVENTORY.md`
- `docs/motivation/B1_REGISTERED_CONTROLLER_SUBJECTS.tsv`
- `docs/motivation/B1_FAMILY_B_GATE_REPORT.md`
- `experiments/motivation/b1_family_b/b1_gate.json`

Inventory PX4 in-tree registration users, mc_nn, RAPTOR, other controllers,
setpoint configuration, allocator-bypass/direct-writer paths, classic
restoration, and already referenced reproducible out-of-tree subjects. Select
or implement a deterministic reference controller only if it is low-cost,
observable, explainable, compatible with the locked registration facility,
and safe in SITL.

If feasible, stop after three normal Classic→Reference→Classic runs and three
controlled local-process/release recovery runs. If not feasible within the
bound, stop with an inventory/scope Gate instead of developing a large new
flight-control module. Direct-actuator flight is excluded.

### M-FINAL — Unified Motivation Completion Gate

Status: `NOT_STARTED`.

Outputs:

- `docs/motivation/MOTIVATION_STUDY_FINAL_REPORT.md`
- `experiments/motivation/motivation_completion_gate.json`
- `docs/narrative/NEW_NARRATIVE_v7.md`
- updates to `docs/narrative/CURRENT_NARRATIVE.md`
- updates to `docs/narrative/SCOPE.md`
- updates to `docs/repository/CURRENT_GOAL_STATE.md`
- final update to `docs/repository/MOTIVATION_COMPLETION_STATE.md`

Evaluate MG1–MG10 using only `PASS`, `CONDITIONAL_PASS`,
`NEGATIVE_SCOPE_DECISION`, or `FAIL`. Keep Method Evaluation Gates—guided
search gain, random comparison, campaign yield, and full fuzzer
effectiveness—explicitly deferred. Select the final Motivation disposition
from the four authorized values and let the machine-readable Gate decide
whether Stateful Testing/Fuzzer v0 is the exact next phase.

Stop after all reports, compact evidence, Gates, tests, validator stages,
integrity checks, pushes, raw-artifact audit, and local-process/port cleanup
pass. Do not automatically begin the next phase.
