# Experiment plan and decision gates

This plan implements the direction in
[NEW_NARRATIVE_v8.md](NEW_NARRATIVE_v8.md). It intentionally specifies the
order and evidence obligations without pretending that the final corpus,
budgets, or sample sizes are already known.

## Current gate

The Motivation and measurement foundation is complete with bounded claims.
The next work is method construction and pilot design, not automatic execution
of an already prepared formal matrix.

In particular, the qualified process-exit candidate remains at zero formal
launches. Readiness does not authorize a denominator. It can be reused only if
it satisfies the new common corpus, baseline, feedback, and statistical
contracts; otherwise it requires a new identity and preregistration.

## Stage 1: implement the full semantic state

Deliver:

- the state schema defined in [ROUTE_MODEL.md](ROUTE_MODEL.md);
- deterministic extraction from normalized evidence;
- lifecycle-phase and ownership progression;
- freshness, health, successor, fallback, motion-context, and bounded-history
  fields;
- replay tests against retained traces; and
- a reduced-observation analysis.

Exit only when equivalent retained evidence produces deterministic state and
the implementation distinguishes route epoch, owner, lifecycle progress, and
command freshness without relying on mode labels.

Status: the state schema, the deterministic extractor, the replay over every
retained admissible trace, and the reduced-observation comparison are
available; the exit checks are computed mechanically by
[the replay analysis](../experiments/stage1_semantic_state_replay_v1/FINAL_REPORT.md)
rather than asserted. What remains for the generator is Stage 3: the live loop
must consume this state instead of the narrower prototype state.

## Stage 2: construct the core action and workload corpus

Build an inventory along two axes:

1. lifecycle phase: registration, activation, execution, completion,
   replacement, fallback, and re-entry;
2. mechanism: process loss/restart, callback or setpoint stall, communication
   delay, health loss, rejection, manual/GCS/failsafe takeover, and adjacent
   authority requests.

For every candidate record:

- public/source/trace provenance;
- reachable preconditions and cleanup;
- the state and contract boundary it can exercise;
- whether it is a benchmark, discovery action, or realism validation;
- implementation and observation requirements; and
- why it is included or excluded from the core corpus.

Real full-stack events receive high investigation priority. An unexplained
event is not ground truth until reproduced and attributed.

Stage 2 freezes a minimal representative corpus only after this inventory. The
number and identity of actions are outputs of the analysis, not assumptions.

## Stage 3: implement closed-loop generation and feedback

Deliver the loop defined in [METHOD.md](METHOD.md): observe, filter, select,
execute, re-observe, update, and continue/reset.

The initial feedback contract records:

- admissible versus inadmissible execution;
- semantic state and transition visitation;
- action and timing coverage;
- contract-boundary coverage; and
- unique candidate signatures sent to confirmation.

Repeated violations of one deliberate stimulus do not count as new findings.
Any numeric prioritization or weighting is selected in pilot work and frozen
before formal evaluation.

## Stage 4: establish benchmark and finding confirmation

Construct separate sets for:

- historical known defects with reproducible provenance;
- current natural candidates promoted after confirmation;
- mechanism-derived seeded faults; and
- newly discovered natural findings.

Every candidate requires independent replay, minimization, measurement checks,
clustering, attribution, and a finding-level label. Seeded and natural cases
are never pooled into one defect count.

## Stage 5: connect the real upper software stack

Use the complete upper mission/behavior stack to:

- collect trace-derived seeds and parameter ranges;
- validate action reachability;
- compare controlled-harness and full-stack behavior; and
- replay representative findings in full-stack closed-loop SITL.

Freeze the task and physical outcomes before replay. HITL and real flight are
optional follow-on validation, not prerequisites for the core study.

## Stage 6: implement baselines and run non-formal pilots

The core methods are:

- grammar-aware bounded random;
- deterministic/systematic enumeration;
- state-conditioned but feedback-free generation; and
- full state- and feedback-guided generation.

Official scenarios are reported separately as a practice reference.

All comparable methods share action grammar, parameter bounds, seeds, reset
semantics, observable outcomes, safety rules, and execution environment. Pilot
work estimates variance, runtime, admissible yield, sequence-length behavior,
and reset cost. It does not enter the formal denominator.

## Stage 7: freeze the formal evaluation

Before any main campaign, preregister:

- one falsifiable thesis and RQ mapping;
- the final core corpus and benchmark;
- method implementations and ablations;
- primary and secondary metrics;
- campaign reset semantics and paired seeds;
- execution/action budget and maximum sequence length;
- wall-clock and computation-cost reporting;
- campaign repetitions, effect sizes, uncertainty, and stopping rules;
- finding replay, minimization, clustering, and attribution; and
- full-stack replay selection criteria.

One complete adaptive campaign is the independent statistical unit. A
campaign starts with empty generator memory and contains multiple episodes.
Launches or episodes inside a campaign are correlated observations, not an
inflated independent sample size.

The primary fairness view uses a fixed execution budget. End-to-end wall-clock
time, analysis cost, reset cost, and safety interruptions are also reported.

## Stage 8: execute, confirm, and report

Execution order is:

1. preflight and accounting registration;
2. safety and collector readiness;
3. environment attestation;
4. live execution and cleanup;
5. barrier until every live attempt in the batch stops;
6. offline evidence processing and Oracle evaluation;
7. compact retention and accounting close; and
8. candidate confirmation and full-stack replay under separate identities.

No offline ULog, clock, Gate, or Oracle processing may overlap another live
attempt in the same batch. Preflight, evidence, environment, or physical-
validity failures are recorded honestly and never promoted to SUT results.

## Metrics and ablations

The metric hierarchy is:

1. distinct confirmed finding or known-defect detection under fixed budget;
2. semantic state, transition, and contract-boundary coverage;
3. actions/episodes/time to finding; and
4. admissible yield, execution cost, and safety interruption.

Required core ablations are:

- no semantic feedback;
- route-identity-only versus full semantic state; and
- timing-only versus action-sequence-plus-timing generation.

Only key Oracle components receive targeted ablation. Additional ablations
must answer an explicit causal question rather than fill a predetermined list.

## Per-experiment requirements

Every flight experiment uses a new plan conforming to the tracked schema. It
must bind:

- unique plan, study, campaign, and attempt identities;
- generation strategy and retained seed;
- source, target, successor, and fallback obligations;
- action grammar, state preconditions, and sequence bounds;
- evidence, physical-validity, safety, and cleanup requirements;
- coverage and finding semantics;
- immutable repository, source, binary, image, method, and configuration
  identities; and
- the actual execution and collector environment attestation.

Templates are not authorization to execute. Any extension to a new action,
route, workload, or strategy requires qualification, preregistration, a new
identity, and a separate denominator.
