# C1 Concurrent Authority Events Report

Date: 2026-07-20

Disposition: `CONDITIONAL_PASS_BOUNDED_LINEARIZATION_CONFORMANCE`

## Executive conclusion

The bounded deterministic probe obtained 14 accepted runs from 17 formal
attempts. Every accepted run passed Authority Event Linearization Oracle 0.2.
No accepted run had a non-linearizable final route, unexplained executor,
post-final old route epoch, competing writer timestamp, route gap above 24 ms,
or incomplete Land/Disarm cleanup. Four event pairs completed all three timing
orders. C1-A/near is measurement-insufficient after both allowed attempts were
observability-rejected, so this report does not claim complete 15-slot
coverage.

The evidence is sufficient to retain the five public event-pair productions
as legal state grammar for later bounded state-space exploration. It is not a
random campaign and provides no comparison between guided and random search.

## Identity and scope

- Preregistration commit:
  `2cb2e021f1604868387f94b5eef6b6457f719416`.
- First formal-attempt revision:
  `6fa55e5256c6b99e20867f7ebca01ef8d06ab1`.
- PX4 revision: `4ae21a5e569d3d89c2f6366688cbacb3e93437c9`.
- Interface revision: `c3e410f035806e8c56246708432ded09c976434b`.
- Vehicle/world: Gazebo SITL `gz_x500` / `default`.
- Test subject: non-replacement External Mode using a zero-velocity
  Trajectory setpoint at 20 Hz and no Mode Executor.

All event inputs used public flight-control interfaces or bounded control of a
locally owned test process. No `nav_state`, executor, or internal failsafe
variable was written directly. Raw ULogs and logs remain ignored under
`runs/motivation/c1_concurrency/`.

## Registered method

Each event pair used event-A-first, near-simultaneous, and event-B-first
orders. Clearly ordered events required at least 250 ms separation and were
requested at 400 ms; near events required at most 100 ms separation. Each slot
allowed two attempts. The total formal cap was 30. A complete-evidence
violation would have triggered at most three minimal confirmation attempts;
none was triggered.

Oracle 0.2 requires visible inputs, registered relative timing, a final route
equivalent to a legal serial order, Autopilot executor `0`, no post-final old
epoch control event, exclusive/continuous writer output, and Land/Disarm
cleanup. Cross-domain selection requires a `VALID` clock bridge and excludes
one measured uncertainty bound at both ends.

## Formal results

| Pair / order | Attempts | Accepted | Final result |
|---|---:|---:|---|
| A activation + Hold / A first | 2 | 1 | PASS, Hold 4 |
| A activation + Hold / near | 2 | 0 | measurement-insufficient at cap |
| A activation + Hold / B first | 1 | 1 | PASS, External 23 |
| B completion + Hold / A first | 1 | 1 | PASS, Hold 4 |
| B completion + Hold / near | 1 | 1 | PASS, Hold 4 |
| B completion + Hold / B first | 1 | 1 | PASS, Hold 4 |
| C local process termination + RTL / A first | 1 | 1 | PASS, RTL 5 |
| C local process termination + RTL / near | 1 | 1 | PASS, RTL 5 |
| C local process termination + RTL / B first | 1 | 1 | PASS, RTL 5 |
| D fallback + re-entry / A first | 1 | 1 | PASS, External 23 |
| D fallback + re-entry / near | 1 | 1 | PASS, External 23 |
| D fallback + re-entry / B first | 1 | 1 | PASS, RTL 5 |
| E release + failsafe clear / A first | 1 | 1 | PASS, RTL 5 |
| E release + failsafe clear / near | 1 | 1 | PASS, RTL 5 |
| E release + failsafe clear / B first | 1 | 1 | PASS, RTL 5 |

Totals: 17 attempts, 14 accepted, two `OBSERVABILITY_REJECTED`, one
`CAMPAIGN_CONFIGURATION_FAILURE`, and zero accepted Oracle violations. The 14
accepted runs all had `VALID` clock bridges and complete pair windows.

## Excluded attempts and amendments

`c1-a-a-first-a01` exposed an offline Oracle 0.1 defect: a 100 ms post-close
buffer admitted cleanup RTL and compared cleanup epoch 6 with the pre-cleanup
Hold epoch 5. It is classified `CAMPAIGN_CONFIGURATION_FAILURE`, and its
original false-positive result remains preserved. Amendment
`C1-ORACLE-001`, commit `4f90d132`, applies a clock-uncertainty-bounded
pre-cleanup window. Diagnostic reanalysis passed but was not promoted into the
accepted denominator.

Both A/near attempts produced only 16 admissible bridge samples, below the
frozen minimum 20, and are `OBSERVABILITY_REJECTED`. The cell closed at its
two-attempt cap. Future-only amendment `C1-HARNESS-002`, commit `48920477`,
adds a ten-sample pre-arm observation warm-up. It changes no threshold, event
order, command, SUT state, seed, or cap and does not reopen A/near.

## Linearization findings

- Pair A establishes the two clear serial endpoints, but its near boundary is
  unmeasured within the registered bound.
- Pair B converged to Hold for all three completion/takeover orders.
- Pair C converged to RTL for all three orders around controlled locally owned
  process termination.
- Pair D resolved fallback-first and near to External re-entry in these runs;
  a request clearly preceding fallback resolved to RTL.
- Pair E resolved to RTL for all release/failsafe-clear orders. In B-first,
  health recovery briefly reactivated External before the later legal release;
  the final route was still linearizable as RTL with complete lineage.

Across accepted runs, the maximum writer gap was 8 ms, competing-writer count
was zero, post-final old-epoch control-event count was zero, and
`executor_in_charge` was always the explainable Autopilot executor `0`.
Maximum observed tilt was 6.526 degrees, below the frozen 45-degree safety
bound; every accepted cleanup landed and disarmed.

## Evidence admissibility

The attempt ledger contains exact starting revisions, seeds, classifications,
timing, final routes, and artifact hashes. Excluded attempts do not enter the
SUT denominator. The amendments preserve original evidence and do not modify
PX4, controller branches, setpoints, failsafe selection, route semantics,
formal thresholds, accepted/rejected rules, seeds, or caps.

At closure, the ignored raw namespace contained 17 attempt directories using
approximately 158 MiB. No raw ULog, Gazebo output, or full trace is tracked.
The tracked processed summary is
`data/processed/motivation/c1_concurrency/c1_summary.json`.

## Limitations

The A/near slot remains measurement-insufficient, results cover one locked
PX4/interface/vehicle configuration, and each accepted slot has one accepted
run. The probe supports deterministic state grammar and attribution
feasibility; it does not estimate event frequency, prove all scheduler
interleavings, or establish state-aware search gain.

## Gate and next phase

The machine-readable Gate is `CONDITIONAL_PASS`: all five event pairs have
accepted evidence, four have complete three-order coverage, and no accepted
violation was found. C1 therefore supports proceeding to the bounded R1 rapid
re-entry/session-rollover probe. It does not authorize a full fuzzer campaign.

## Validation and cleanup

Focused C1 tests passed 10/10. The full repository validator passed all 15
stages with 216 tests and 49 checked local links; `tracked_runs=0`. Protected
P5 v6, Issue #162, and Freshness hashes matched their frozen values. The 17
raw attempt directories are ignored, no raw artifact is tracked, no local
PX4/Gazebo/Agent/probe process remains, and local UDP port 8888 is unoccupied.
