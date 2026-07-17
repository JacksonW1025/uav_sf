# Fitness v0

## Ordering

Fitness never overrides validity. Scheduler ordering is lexicographic:

```text
valid SUT outcome
  > measurement unknown
  > invalid input or setup
  > environment failure
```

Only valid SUT outcomes receive positive contract, novelty, or physical terms.
Environment crashes, missing logs, invalid clocks, incomplete critical windows,
and duplicates are penalties and cannot become high-fitness discoveries.

## Contract objective

The primary score is the maximum normalized distance across the five Oracle 0.3
clauses. A clause violation adds a fixed confirmation bonus only after the oracle
has complete required evidence.

```text
revocation = old-epoch post-revocation lateness / deadline
installation = target installation lateness / deadline
exclusivity = measured overlap / exclusivity resolution
continuity = unowned gap / allowed gap
recovery = maximum(recovery incompleteness terms)
```

Distances are clipped to `[0, 4]` to prevent one extreme measurement from starving
novel schedules. `UNKNOWN` clause states provide no violation bonus and incur the
measurement penalty. `NOT_APPLICABLE` contributes neither reward nor penalty.

## Auxiliary objectives

Novelty is the number of previously unseen route/state bins and transition
sequence n-grams, normalized to `[0, 1]`. Physical severity uses bounded altitude
loss, tilt, position error, and recovery duration, normalized by the safe envelope;
it is capped and is never sufficient to call a contract violation.

The scalar within the valid tier is:

```text
10.0 * clause_violation_count
+ 2.0 * maximum_contract_distance
+ 1.0 * route_state_novelty
+ 0.5 * sequence_novelty
+ 0.25 * bounded_physical_severity
- penalties
```

Penalties are 4.0 for measurement unknown, 6.0 for invalid scenarios, 8.0 for
environment failure, and 2.0 for a duplicate. These values affect scheduling only;
classification remains explicit in the result record.

## Measurement uncertainty

A metric cannot contribute positive threshold distance unless its excess is above
the recorded uncertainty bound. Distances within uncertainty are zero. Timing uses
the per-run clock/fault bound; physical metrics use their same-unit monitor
resolution model. Missing uncertainty makes the term unavailable rather than zero.

## Discovery boundary

Raw oracle violations are candidates. Fitness does not establish reproducibility,
root cause, or defect status. Replay, minimization, canonical-build reproduction,
source attribution, and competing-explanation review remain mandatory. Mutant
profiles can test whether the known target ranks highly but their scores are never
included in canonical smoke results.
