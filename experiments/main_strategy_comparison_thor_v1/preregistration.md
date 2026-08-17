# Fixed-budget live strategy comparison preregistration

Status before formal execution: **FROZEN / NOT YET RUN**.

## Place in the paper

This study is the first executable vertical slice of paper Section 7, the Main
Evaluation. It follows the completed Section 6 Motivation Study. It tests the
method's live action-selection backend on the already qualified A2 moving
workload; it is not a replacement for the later full route-corpus evaluation.

## Frozen question and claim boundary

Under one equal launch budget, can all three strategy implementations execute
valid state-conditioned actions and produce admissible contract evidence, and
do their executed timing-boundary and violation-signature coverages differ in
this single healthy setpoint-stall action?

The study may support only a fixed-budget implementation and coverage result.
It cannot establish general search superiority, PX4 defect prevalence,
real-flight risk, mechanism ranking, or full Main Evaluation completion.

## Denominator and execution order

The denominator is exactly 18 launches: two mechanisms by three strategies by
three launches. Every cell is `fixed_budget` with target/cap 3/3; accepted
evidence never causes early stopping. The runner executes three strategy arms
in parallel within each mechanism and ordinal, places an all-live-complete
barrier before processing, and closes every launched attempt in the append-only
ledger.

The three strategies are:

- official sequence: fixed 5.0 s action offset;
- bounded random timing: a preregistered seed selects an offset uniformly
  within 3.5--6.5 s;
- state-aware: the next candidate uses only earlier observed
  `action_requested` boundary coverage from the same mechanism-strategy cell.

All arms use the same action (`setpoint_stall`), moving position-only profile,
simulation seed by ordinal, thresholds, safety limits, observer, and successor.
An action is executable only after observed route activation and motion entry.

## Frozen outcomes

The primary implementation outcomes are launch count, accepted/admissible
evidence yield, successful action-request count, and request timing error. The
primary comparison outcomes are executed timing-boundary coverage, applicable
contract-boundary coverage, violation-signature coverage, and launches to first
violation. Results are reported per mechanism and strategy; no failed launch is
silently replaced.

## Qualification and identities

The prerequisite qualification is `PASS`: 6/6 non-formal flights were accepted,
admissible, and physically valid. Those flights remain outside this study.

- Study: `main-strategy-comparison-thor-v1`
- Environment: `thor-r38.2.1-main-strategy-v1`
- Revision: `ea2381c8cecfe2b885a92a68b5c803481da3e6e2`
- Image: `sha256:0900076eea14aecfbe446d2adc6458f5eec80f4feb3cf564b388d92bf7e8eee5`
- Formal concurrency: 4
- Maximum clock uncertainty: 20 ms

`matrix.json`, the environment attestation, method configuration, safety
configuration, and strategy configuration are immutable inputs after this
preregistration commit is pushed. Any identity mismatch is a configuration
failure rather than a reason to alter the matrix.
