# Family A Fuzzer v0 preregistration

Status: `PREREGISTERED_NOT_ACTIVATED`

Qualification activation: `DECLINE_IMPLEMENTATION_NOT_READY`

Qualification status: `QUALIFICATION_NOT_AUTHORIZED`

This directory is the frozen, machine-verifiable preregistration for a future
controlled SITL study of flight-software reliability, runtime consistency,
route conformance, command freshness, lifecycle progression, and state-aware
testing. It contains zero formal attempts and authorizes no runtime.

## Artifact index

| Artifact | Frozen role |
|---|---|
| [preregistration](preregistration.yaml) | Family A scope, claims, comparison contract, and non-collapsing semantics |
| [source lock](source_lock.yaml) | starting repository, dependency, accepted evidence, and revision identities |
| [seed catalog](seed_catalog.tsv) | admitted current runtime seeds, historical replay benchmark, and excluded candidates |
| [state model](state_model.yaml) | route epoch, producer/session, lifecycle, freshness, lineage, and evidence state |
| [event grammar](event_grammar.yaml) | reachable public PX4 lifecycle event edges and legal source predicates |
| [mutation grammar](mutation_grammar.yaml) | bounded timing variation, event order, health/setpoint, and accepted motion-context operators |
| [strategy matrix](strategy_matrix.yaml) | official sequence, bounded random timing comparator, and state-aware mutation |
| [campaign matrix](campaign_matrix.yaml) | equal future budgets, qualification prerequisite, and stop rules |
| [Oracle lock](oracle_lock.yaml) | Oracle, schema, route profile, clock bridge, and evidence admissibility identities |
| [evidence rules](evidence_rules.yaml) | attempt registration, acceptance, rejection, finding, deterministic replay, and accounting rules |
| [safety rules](safety_rules.yaml) | frozen physical, runtime, observation, cleanup, and process boundaries |
| [analysis plan](analysis_plan.yaml) | coverage, evidence yield, search signal, realism, attribution, and comparison metrics |
| [activation Gate](activation_gate.json) | closed activation and runtime authorization state |
| [attempt ledger](attempt_ledger.yaml) | append-only future accounting, currently zero |
| [adjudication template](final_adjudication_template.yaml) | future results structure without a predeclared result |
| [activation review](activation_review/README.md) | independent qualification readiness review and decline decision |
| [readiness amendment](readiness_amendment/README.md) | independent static resolution of the 11 activation-review blockers without runtime authorization |

The machine Gate is validated against the
[activation Gate schema](../../../data/schemas/family_a_fuzzer_v0_activation_gate.schema.json).
The [consistency checker](../../../scripts/validation/check_family_a_fuzzer_v0_preregistration.py)
and [focused tests](../../../tests/test_family_a_fuzzer_v0_preregistration.py)
enforce the freeze.

## Frozen boundary

Only Family A is admitted. Current runtime seeds come from accepted P0, P0-D,
P2, P3, P5 v6, Freshness F1–F4, N1, and C1 evidence. P0-D is only a clean
re-entry baseline. Issue #162 is `HISTORICAL_REPLAY_ONLY` and can be used only
for deterministic replay of processed artifacts; it cannot enter current
runtime or the current natural finding denominator.

R1 session rollover, W1 real-workload runtime, Family B, direct actuator,
unsupported replacement/executor composition, delayed old-session messages,
HITL, real flight, stress-only primary input, and unbounded campaigns are
excluded. The earlier pre-M-FINAL prototype, its 200-evaluation plan, its Route
Oracle 0.3 identity, and its validation-only mutant seeds are not authoritative
for this preregistration.

Each future strategy arm has a maximum of 12 formal attempts and requires at
least 8 accepted attempts for a strategy comparison. The total future
comparison maximum is 36. Rejected attempts consume the arm budget, unused
budget does not transfer, and no attempt is replaced automatically.

## Current Gate

- campaign activated: `false`
- runtime authorized: `false`
- formal attempts authorized: `false`
- formal attempts: `0`
- activation commit: `null`
- state-aware search gain: `NOT_ESTABLISHED`
- full method effectiveness: `NOT_ESTABLISHED`
- qualification authorized: `false`
- qualification formal attempts: `0`
- comparison arms authorized: `false`

The independent activation review found 11 blocking clauses and decided
`DECLINE_IMPLEMENTATION_NOT_READY`. The original activation Gate and decision
remain frozen and closed. A subsequent readiness amendment now records
`READINESS_RESOLVED_PENDING_INDEPENDENT_REVIEW` with 11 resolved and zero
remaining implementation/environment blockers. This static readiness result
does not authorize qualification or runtime.

The next exact action is to perform a new independent static qualification
activation review. No Family A Fuzzer v0 runtime has executed.
