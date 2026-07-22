# R1 Rapid Re-entry and Session Rollover Report

Date: 2026-07-21

Disposition: `MEASUREMENT_INSUFFICIENT_AT_R1_A_ATTEMPT_LIMIT`

## Executive conclusion

R1 stopped under its registered rule when R1-A reached six attempts with zero
accepted runs. All six attempts are excluded `FORMAL_SAFETY_STOP` results. The
first attempt ended when PX4 aborted on a pthread mutex-owner assertion after
the new component registered. Attempts 2–6 completed Land/Disarm after the
configured fallback RTL reached ground contact before the new session became
active, which crossed the frozen pre-cleanup safety boundary.

No attempt established the complete new-session observation window, so no
Session Rollover Oracle result was produced and no `PASS`, `EXPOSURE`, or
`VIOLATION` entered a scientific denominator. R1-B and R1-C were not started
because the relevant R1-A cap had already stopped the ordered matrix. The
result is bounded measurement insufficiency, not evidence for or against
session isolation.

## Frozen identity and method

- Preregistration commit:
  `9faad09d0e9e7631497034e7ee27f8ab2ce9d896`.
- Formal-attempt starting revision:
  `ca875a19290cfb25008e34f7eafab369a71aac06`.
- PX4 / `px4_msgs` / interface revisions:
  `4ae21a5e569d3d89c2f6366688cbacb3e93437c9` /
  `18ecff03041c6f8d8a0012fbc63af0b23dd60af1` /
  `c3e410f035806e8c56246708432ded09c976434b`.
- Vehicle/world: local Gazebo SITL `gz_x500` / `default`.
- Contract: class B, implied lifecycle ownership and progression without an
  explicit registration-generation guarantee.
- Selected R1-C semantic: `ModeCompleted`; no other delayed semantic was used.

Every attempt used the next frozen R1-A seed, a clean pushed worktree, exact
tracked-artifact and local-binary hashes, public PX4/ROS 2 interfaces, and only
locally owned test processes. No PX4 registration table, `nav_state`, executor,
failsafe variable, controller memory, or internal state was written directly.

## Formal attempt accounting

| Attempt | Seed | Accepted | Disposition | Terminal evidence |
|---|---:|---:|---|---|
| `r1-a-a01` | 410101 | no | `FORMAL_SAFETY_STOP` | PX4 abort after new registration; new activation/window and SUT cleanup state unavailable |
| `r1-a-a02` | 410102 | no | `FORMAL_SAFETY_STOP` | ground contact before new activation; Land/Disarm complete |
| `r1-a-a03` | 410103 | no | `FORMAL_SAFETY_STOP` | ground contact before new activation; Land/Disarm complete |
| `r1-a-a04` | 410104 | no | `FORMAL_SAFETY_STOP` | ground contact before new activation; Land/Disarm complete |
| `r1-a-a05` | 410105 | no | `FORMAL_SAFETY_STOP` | ground contact before new activation; Land/Disarm complete |
| `r1-a-a06` | 410106 | no | `FORMAL_SAFETY_STOP` | ground contact before new activation; Land/Disarm complete |

Attempts 2–6 recorded 50–53 clock samples, complete old registration and
activation identity, correlated new registration request/reply identity, and
new mode/executor assignments. They did not record a new activation key,
complete route/lineage window, or admissible Oracle result. Maximum recorded
tilt across those attempts was 4.689 degrees and maximum recorded angular rate
was 0 rad/s; those values do not turn the excluded attempts into accepted
outcomes.

## Stop rule and unexecuted scenarios

R1-A required three accepted runs and allowed no more than six attempts. Its
0/3 accepted count at 6/6 attempts closes the scenario as
`ATTEMPT_LIMIT_REACHED_MEASUREMENT_INSUFFICIENT`. The preregistered matrix
stops when all targets are reached or a relevant scenario cap is reached.
Therefore the total is 0 accepted from 6 attempts, not an invitation to use
unused R1-B or R1-C seeds.

R1-B and R1-C each remain 0 attempts / 0 accepted. No completion value was
held or released, and the completion-session isolation clause was never
applicable to measured evidence.

## Claim boundary

This Gate makes no route/session conformance claim and proves no lifecycle
ownership violation. In particular:

- the PX4 abort and five pre-window landings are excluded safety-stop
  observations, not Session Rollover Oracle `VIOLATION` results;
- no accepted R1-A evidence exists, and R1-B/R1-C were not measured;
- no conclusion is available about whether an earlier-associated completion
  would be ignored, remain identity-ambiguous, or progress a successor;
- bounded non-observation is not proof of absence;
- the local SITL observations do not establish physical consequence,
  population frequency, or behavior on another vehicle, world, or transport;
- the current-version R1 result does not revise the frozen historical Issue
  #162 benchmark; and
- R1 provides no evidence that Stateful Fuzzing improves search.

The public `ModeCompleted` message still lacks an instance/generation field as
documented by the frozen semantic audit. That design fact is not promoted into
an R1 `EXPOSURE` because no accepted R1-C ambiguity window was executed.

## Evidence and integrity

The finalized [matrix](../../experiments/motivation/r1_session/matrix.yaml) and
[attempt ledger](../../experiments/motivation/r1_session/attempt_ledger.yaml)
record the exact revision, seeds, classifications, clock counts, cleanup
states, physical summaries, and raw-artifact hashes. The compact tracked
[summary](../../data/processed/motivation/r1_session/r1_summary.json) contains
only closure aggregates. The six raw directories remain ignored under
`runs/motivation/r1_session/` and occupied approximately 800 KiB at closure;
no raw log, ULog, simulator output, build product, or `runs/` file is tracked.

The design contract remains in the [Session Rollover Oracle](../design/SESSION_ROLLOVER_ORACLE.md)
and [R1 semantic audit](R1_SESSION_SEMANTIC_AUDIT.md). The machine-readable
[R1 Gate](../../experiments/motivation/r1_session/r1_gate.json) preserves the
same measurement-insufficient disposition and claim boundary.

## Validation, cleanup, and next phase

Final artifact-rich validation passed all 16 R1-focused tests and all 15
repository-validator stages with 232 tests and 55 checked local links. The
clean-checkout equivalent passed 15 R1 tests with one explicit local-binary
skip, then all 15 validator stages with 227 passed and five explicit
local-artifact skips. Structured data, protected evidence, raw-artifact hashes,
tracked-file audits, and the 10 MiB file limit passed. After the last attempt,
no PX4, Gazebo, Micro XRCE-DDS Agent, R1 probe, or monitor process remained and
UDP port 8888 was unoccupied.

The exact next registered Motivation phase is W1, the bounded real-workload
runtime/trace spike. W1 was not started by this closure.
