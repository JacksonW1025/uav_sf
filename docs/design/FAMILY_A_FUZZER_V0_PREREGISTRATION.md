# Family A Fuzzer v0 preregistration

Status: `PREREGISTERED_NOT_ACTIVATED`

The Family A Fuzzer v0 preregistration freezes a future controlled SITL study
before any runtime or formal attempt. Its purpose is to compare three bounded
strategies for flight-software reliability and runtime consistency while
preserving route conformance, command freshness, lifecycle progression,
evidence admissibility, and deterministic replay semantics.

The preregistration is independent of the earlier pre-M-FINAL prototype. The
old 200-evaluation plan, Route Oracle 0.3 identity, validation-only synthetic or
mutant seeds, and prior activation concepts do not enter this freeze.

## Authority and current state

The [M-FINAL machine Gate](../../experiments/motivation/m_final/motivation_completion_gate.json)
authorizes creation and push of an independent Family A preregistration only.
It does not authorize implementation or execution. The
[source lock](../../experiments/fuzzer_v0/family_a/source_lock.yaml) starts at
repository commit `38725e87d8d0ebe03b1fe1712055725338332d83`, locks the
current PX4 and interface revisions, and protects the M-FINAL authority chain.

The [activation Gate](../../experiments/fuzzer_v0/family_a/activation_gate.json)
remains closed. Campaign activation, runtime authorization, and formal-attempt
authorization are all false. The
[attempt ledger](../../experiments/fuzzer_v0/family_a/attempt_ledger.yaml) is
`NOT_STARTED`, has no activation commit, and contains zero attempts.

## Family A scope and accepted seeds

The frozen scope includes PX4 internal routes, Legacy Offboard, Dynamic
External Mode, Mode Executor, External Mode Replacement where supported by the
current interface, supported internal fallback, RC or GCS mode requests,
supported failsafe behavior, controlled local process interruption,
health/proof-of-life state, setpoint publication state, command lineage,
completion, and successor progression. Admitted setpoint levels are trajectory
or position/velocity, attitude, and body rate where accepted evidence and
observation support exist.

The [seed catalog](../../experiments/fuzzer_v0/family_a/seed_catalog.tsv)
contains 61 audited records:

- 50 `ACCEPTED_RUNTIME_SEED` rows from accepted current Family A evidence;
- 1 `ACCEPTED_REPLAY_BENCHMARK` row for Issue #162 processed-artifact replay;
- 10 `EXCLUDED` rows that preserve rejected scope decisions and provenance.

Issue #162 is historical replay only. R1, W1, B1, Family B, direct actuator,
reduced-observation confirmation, current constructor prevention, and
validation-only mutant candidates cannot enter the current runtime pool.

## Runtime state and reachable grammar

The [state model](../../experiments/fuzzer_v0/family_a/state_model.yaml) freezes
33 semantic fields. It distinguishes route epoch, activation, registration
instance, producer session, lifecycle and executor ownership, setpoint level,
command-age bucket, controller/allocator/writer lineage, health/setpoint state,
failsafe state, completion and successor state, task and vehicle context,
evidence completeness, and clock-bridge validity. Run IDs, attempt IDs, host
timestamps, artifact paths, and process IDs do not participate in semantic
state identity.

Command age is divided into `FRESH`, `RETAINED_SHORT`, `RETAINED_MEDIUM`,
`RETAINED_LONG`, `POST_REVOCATION`, and `UNKNOWN`. The numerical boundaries are
derived from accepted 20 Hz setpoint publication, the frozen route continuity
period policy, the accepted 1 s Offboard loss configuration, and the accepted
1500 ms Dynamic External Mode health-loss deadline. `POST_REVOCATION` has
semantic precedence over numerical age, and missing lineage or valid time
mapping produces `UNKNOWN`.

The [event grammar](../../experiments/fuzzer_v0/family_a/event_grammar.yaml)
freezes 26 reachable edges. Every edge requires a legal source-state predicate,
a public PX4 lifecycle event or owned local-process trigger, expected control-,
route-, data-, and owner-plane effects, legal and prohibited successors,
applicable Oracles, realism, cleanup, and accepted provenance. Initial v0 cases
contain no more than two authority/lifecycle events and pair compositions must
come from accepted C1 provenance.

## Bounded variation and strategies

The [mutation grammar](../../experiments/fuzzer_v0/family_a/mutation_grammar.yaml)
freezes 27 operators. They cover bounded timing variation, accepted event
orders, controlled process stop or pause, callback/setpoint stall,
health/setpoint decoupling, and accepted motion and setpoint contexts. DDS
delay/drop/reorder, ascent, and active acceleration/braking parameterization
remain disabled because current accepted Family A evidence does not freeze a
suitable formal domain. Acceleration or braking may still be observed and
classified as vehicle-state context; the strategy may not synthesize an
unregistered command range for them.

The three strategies in the
[strategy matrix](../../experiments/fuzzer_v0/family_a/strategy_matrix.yaml)
share the same seed pool, reachable grammar, simulator, vehicle, revision,
adapter identity, Oracle suite, evidence Gate, cleanup, and formal budget:

1. `OFFICIAL_SEQUENCE` deterministically parameterizes accepted official or
   baseline sequences and does not search new timing.
2. `BOUNDED_RANDOM_TIMING_COMPARATOR` samples only materialized legal tuples
   within the frozen grammar and parameter domains.
3. `STATE_AWARE_MUTATION` uses a frozen lexicographic selection rule that
   prioritizes uncovered admissible route/lifecycle/freshness states and Oracle
   applicability before reproduction count.

Each arm has a future maximum of 12 formal attempts and a minimum of 8 accepted
attempts for comparison. The future comparison maximum is 36. A separate
qualification phase targets 3 accepted attempts with a maximum of 6, but it is
not part of the comparison budget and is not authorized by this preregistration.

## Oracle, evidence, and safety freeze

The [Oracle lock](../../experiments/fuzzer_v0/family_a/oracle_lock.yaml) records
the exact specifications, executable hashes, schema hashes, profiles,
thresholds, clock bridge, route gap/overlap policy, freshness classification,
successor timing policy, and evidence rejection rules for:

- Route Oracle 0.4;
- Pre-Revocation Freshness Oracle 0.1;
- Successor Progression Oracle 0.1;
- Authority Event Linearization Oracle 0.2 for accepted C1 pairs; and
- Family A Fuzzer v0 Evidence Admissibility Gate 1.0.

`UNKNOWN` and `NOT_APPLICABLE` never become PASS. `EXPOSURE` never becomes
`VIOLATION`. Rejected attempts do not enter a SUT outcome denominator, cleanup
is separate from the formal target window, historical replay is separate from
current runtime, and duplicate signatures increase only reproduction count.

The [evidence rules](../../experiments/fuzzer_v0/family_a/evidence_rules.yaml)
require pre-registration of every future attempt, immutable unique IDs, exact
source and revision identity, retained raw artifacts in ignored storage,
compact evidence, a complete target window, valid clock mapping where needed,
complete route/lifecycle lineage, and a cleanup audit. Missing critical evidence
is rejected; it is never guessed.

The [safety rules](../../experiments/fuzzer_v0/family_a/safety_rules.yaml) reuse
accepted Family A commands and formal safety-monitor bounds. They cover PX4
abort, simulator clock stall, non-finite values, height, horizontal and vertical
speed, attitude, body rate, unexpected ground contact, incomplete target and
cleanup windows, invalid clocks, missing epochs or lineage, illegal overlap,
route gaps, runner timeout, residual local processes, and occupied campaign
ports. W1 and Family B envelopes are not used.

## Analysis and claim boundary

The [analysis plan](../../experiments/fuzzer_v0/family_a/analysis_plan.yaml)
freezes coverage, evidence yield, search signal, realism, attribution, and
equal-budget comparison metrics. A strategy arm with fewer than 8 accepted
attempts is `MEASUREMENT_INSUFFICIENT`; no strong strategy superiority claim is
allowed, and a higher accepted count in another arm is not automatically search
gain.

Finding signatures include revision, route pair and epoch relation, Oracle and
clause, producer/session relation, command-age bucket, executor-owner and
writer-lineage relations, fallback/successor outcome, and event order.
Minimization may only remove irrelevant events, shorten timing within the
frozen domain, simplify accepted motion context, or lower Reality Distance
while preserving the same Oracle signature.

This preregistration establishes no state-aware search gain and no full method
effectiveness result. Its next exact action is: review the frozen Family A
Fuzzer v0 preregistration and create a separate activation decision.
