# Validity and Environment Failures

## Evidence checks

Every evaluation checks, in order:

1. case schema and semantic grammar;
2. canonical dependency/profile selection and setup;
3. PX4 and Gazebo liveness;
4. successful arming and source-route activation;
5. requested fault/channel event delivery;
6. observable target or fallback route;
7. expected ULog and compact trace production;
8. valid clock bridge or bounded fault marker when cross-domain evidence is used;
9. complete critical transition window and candidate-writer coverage;
10. Route Oracle 0.3 result.

The first failed category determines the classification. Later evidence is kept
for diagnosis but cannot promote the result.

## Classifier

- `INVALID_INPUT`: schema, grammar, range, or route/mechanism incompatibility.
- `INVALID_SETUP`: the requested valid case did not establish its initial state,
  arm, activate its source route, or deliver its requested event.
- `ENVIRONMENT_FAILURE`: PX4, Gazebo, DDS agent, runner, storage, or watchdog
  failed independently of a valid route-contract observation; this includes a
  missing expected ULog after infrastructure failure.
- `MEASUREMENT_UNKNOWN`: the scenario ran, but clock, trace, critical-window,
  writer coverage, or required oracle evidence is insufficient.
- `SUT_PASS`: all validity checks pass and no applicable oracle clause violates.
- `SUT_VIOLATION`: all validity checks pass and at least one applicable oracle
  clause is `VIOLATION`.
- `VALID` is the internal pre-oracle state recorded before conversion to either
  SUT outcome.

`UNKNOWN` is never converted to pass. A SUT violation cannot be emitted from an
environment failure or invalid scenario.

## Retry policy

Environment failures are preserved with their artifacts. The smoke executor may
retry the same case once when the watchdog identifies a transient environment
failure; both evaluations count against the campaign cap. Input/setup and
measurement failures are not silently retried. Consecutive environment failures
at the configured threshold stop the campaign.

## Replay classification

A candidate is replayed three times with its canonical case, simulator seed, build,
and dependency profile:

- `REPRODUCIBLE`: three valid runs violate the same target clause.
- `FLAKY`: at least one valid run matches and at least one valid run does not.
- `NOT_REPRODUCED`: valid replays complete but none match.
- `ENVIRONMENT_FAILURE`: infrastructure prevents the required valid replay set;
  the candidate is not confirmed.

All raw replay attempts remain indexed. A replay environment failure does not count
as contrary SUT evidence, but it also cannot satisfy reproducibility.

## Minimization validity

Each reduction is schema- and grammar-validated before execution. It replaces the
current case only after the configured replay predicate preserves the identical
target clause, source/target route, and route-epoch signature. A smaller UNKNOWN,
invalid, or environment-failing case is rejected. The minimizer has a bounded
evaluation budget and reports the best confirmed case if the budget expires.

## Reporting

Campaign summaries report total evaluations, valid SUT outcomes, invalid inputs,
invalid setups, environment failures, measurement unknowns, passes, raw candidates,
replay classifications, and unique minimized violations separately. Failed and
unknown artifacts are never deleted to improve rates.
