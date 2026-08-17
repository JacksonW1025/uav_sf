# Stage A2 remediation final report

Status: **COMPLETE WITH BOUNDED CLAIMS**.

This study is the independently preregistered remediation of the closed
primary Stage A2 study. It does not extend or rewrite the primary ledger. The
primary study remains `MEASUREMENT_INSUFFICIENT` at 51 launches; this study has
its own image, environment identity, seeds, ledger, and denominator.

## Formal accounting

The remediation closed 26 formal launches with no retry:

| Cell | Launches | Accepted | Oracle result |
| --- | ---: | ---: | --- |
| normal / Legacy Offboard | 5 | 5 | 5 PASS |
| normal / Dynamic External Mode | 5 | 5 | 5 PASS |
| healthy stall / Legacy Offboard | 8 | 8 | 8 VIOLATION |
| healthy stall / Dynamic External Mode | 8 | 8 | 8 VIOLATION |
| Total | 26 | 26 | 10 PASS / 16 VIOLATION |

All 26 traces are `ADMISSIBLE` and pass the registered physical-execution
contract. Every stall result violates only the 200 ms freshness clause. Route
conformance and applicable successor clauses pass. A deliberate fault that
produces admissible violation evidence is an accepted experiment, not a
failed launch.

The hash-chained ledger contains 78 events and ends at
`b748cb11289188b8692920951df7edd7c5acd3d569a1b3eddf2dc4a1a6e15515`.
The study summary and every compact-evidence digest verify against that
ledger.

## Physical consequence

The position-only workload freezes at the last position target when the
setpoint stream stops. It therefore tests retained-target exposure without
introducing an unbounded velocity command.

| Stratum | Median final x (m) | Median planned-profile shortfall (m) | Median post-stall travel (m) |
| --- | ---: | ---: | ---: |
| normal / Legacy Offboard | 3.575 | -0.075 | 0.000 |
| normal / Dynamic External Mode | 3.581 | -0.081 | 0.000 |
| healthy stall / Legacy Offboard | 3.041 | 0.459 | 1.033 |
| healthy stall / Dynamic External Mode | 3.028 | 0.472 | 1.012 |

The negative normal shortfall is a small endpoint overshoot. After the
registered five-second stall boundary, Legacy Offboard moves a median 1.033 m
over 3.223 s and Dynamic External Mode moves a median 1.012 m over 3.114 s,
then both stabilize near the frozen 3.0 m target. The corresponding median
maximum cross-track errors are 0.072 m and 0.064 m. Land recovery path length
is about 3.1--3.2 m because that metric includes the vertical descent; it is
kept separate from the fault-exposure window.

The 13 same-seed mechanism pairs agree on Oracle status. In the eight stall
pairs, the median Dynamic-minus-Offboard difference is -0.028 m for exposure
distance and -0.248 m-s for integrated absolute along-track error. These small
descriptive differences have no registered superiority threshold and do not
support a mechanism safety ranking.

## Motivation result

Stage A2 adds physical interpretability to the Stage A1 freshness finding.
With a constant Stage A1 position target, a stale numerical reference can be
identical to a fresh one. In the moving Stage A2 task, the healthy stall
produces an observable retained-target segment and an approximately
0.46--0.47 m shortfall relative to the complete 3.5 m profile. It does not add
a new violation class: the only new-study violations are the deliberately
exercised freshness obligation.

This is evidence of bounded task-progress consequence in the attested Thor
SITL workload. It is not evidence of flyaway, collision, real-flight risk,
PX4 defect prevalence, a general PX4 bug, or superiority of either external
control mechanism.

## Paper placement and resulting repository state

This result closes paper Section 6, `Motivation Study`, including the Gate 4b
moving-workload realism bridge. Stage A1 remains frozen at its original
`200 / 151 / 94 / 57` accounting. Stage A2 is complete through this independent
remediation while the insufficient primary study remains visible.

Paper Section 7, `Main Evaluation`, remains pending. The present study uses
only Official Sequence and cannot support claims about bounded-random or
state-aware generation effectiveness.

Machine-readable inputs and results are in `summary.json` and
`physical-analysis/`. The physical input manifest binds each plan, closed
trace, workload lifecycle, telemetry stream, raw manifest, and frozen Oracle
evaluation by SHA-256 digest.
