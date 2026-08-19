# Current status

Last narrative alignment: 2026-08-18. The research direction is defined in
[NEW_NARRATIVE_v8.md](NEW_NARRATIVE_v8.md). This file records facts available
in the current repository and deliberately separates completed evidence from
the target method.

## Executive status

```text
Retained Thor formal launches across separate closed studies: 295
Retained historical/Orin results in the current branch: 0
Motivation and measurement foundation: complete with bounded claims
Full semantic-state generation method: not implemented
Main method evaluation: not complete
Formal campaign currently running: none
Process-exit candidate: qualified and preregistered, zero formal launches
```

The 295 launches are a repository total, not one pooled experiment. Every
study retains its own identity, matrix, ledger, thresholds, and denominator.

## Formal study accounting

| Study | Formal launches | Admissible/accepted evidence | Result boundary |
| --- | ---: | ---: | --- |
| Stage A1 primary | 180 | 131 | 75 PASS, 56 VIOLATION; two invalid-plan cells did not reach target |
| Stage A1 supplemental | 20 | 20 | 19 PASS, 1 VIOLATION under an independent remediation identity |
| Stage A2 primary | 51 | 18 | Permanently `MEASUREMENT_INSUFFICIENT`; 31 observability rejection and 2 inconclusive |
| Stage A2 remediation | 26 | 26 | 10 normal PASS, 16 deliberate freshness VIOLATION |
| Setpoint-stall strategy slice | 18 | 18 | 18 deliberate freshness VIOLATION; bounded timing comparison only |

The sum is 295 closed formal launches. Stage A1 alone has the combined
`200 / 151 / 94 / 57` accounting. Stage A2 and the strategy slice are not
added to that denominator.

## Stage A1: measurement and Motivation foundation

The primary study closed 180 launches: 131 accepted, 20 observability
rejections, 28 timeouts, and one environment failure. Nineteen cells reached
target; two invalid-plan cells reached their cap.

The independently preregistered supplemental study corrected only those
plan/fixture obligations. It closed 20/20 new launches as accepted and reached
both 10/10 targets without modifying the primary ledger.

Across both studies, 151 accepted/admissible traces contain 94 overall PASS
and 57 overall VIOLATION. These counts support the following bounded facts:

- mode and terminal outcome do not establish complete authority handoff;
- Route and Freshness are independent evidence dimensions;
- successor installation and completion/request order are independent facts;
- repeated use of one route name requires epoch and activation identity; and
- evidence, environment, and clock failures must not become SUT results.

The counts are not a defect rate. A violation trace is not automatically a
source-grounded PX4 defect.

Evidence:

- [primary report](../experiments/motivation_thor_v1/FINAL_REPORT.md)
- [supplemental report](../experiments/motivation_thor_remediation_v1/FINAL_REPORT.md)

## Stage A1 physical-validity audit

A digest-bound post-hoc audit found that 12 of the 151 admissible Stage A1
traces reached no more than 0.08 m above their local-position origin. They
include 3 PASS and 9 VIOLATION traces. The frozen Stage A1 result is unchanged,
but physical interpretation is limited.

This established an additional rule: evidence admissibility does not by itself
prove that the intended physical task executed. Later plans require sustained
takeoff, valid local position, motion-phase entry, minimum progress, and
profile coverage where applicable.

Evidence: [physical-validity report](../experiments/posthoc_physical_execution_validity_v1/FINAL_REPORT.md).

## Stage A2: moving-workload realism bridge

The Stage A2 primary study closed at 51 launches but remains
`MEASUREMENT_INSUFFICIENT` because a command-subject clock-closure defect
prevented three cells from reaching target. Its result and ledger remain
unchanged.

An independent remediation changed only the evidence-closure rule and the
public takeoff-before-transition obligation. It closed 26/26 formal launches
as accepted and admissible:

- 5/5 normal Legacy Offboard PASS;
- 5/5 normal Dynamic External Mode PASS;
- 8/8 Legacy Offboard healthy-stall freshness VIOLATION; and
- 8/8 Dynamic External Mode healthy-stall freshness VIOLATION.

All 16 deliberate violations are freshness-only; applicable route and
successor clauses pass. The moving task adds physical interpretability without
creating a new violation class:

- median motion after the stall boundary is approximately 1.033 m and 1.012 m;
- median task-progress shortfall is approximately 0.459 m and 0.472 m; and
- no mechanism-superiority threshold was preregistered.

The result does not establish flyaway, real-flight danger, or a general PX4
defect.

Evidence:

- [primary Stage A2 report](../experiments/motivation_stage_a2_thor_v1/FINAL_REPORT.md)
- [remediation report](../experiments/motivation_stage_a2_thor_remediation_v1/FINAL_REPORT.md)

## Completed generation vertical slice

The separately preregistered setpoint-stall comparison closed 18/18 formal
launches across two mechanisms, three strategies, and three launches per cell.
Every attempt is accepted, admissible, physically valid, and a deliberate
freshness VIOLATION.

Observed timing-bin coverage was:

- official sequence: one fixed boundary bin;
- bounded random: three bins; and
- current state-aware prototype: three bins.

The prototype consumed prior live coverage when making later decisions, so
the feedback loop is executable. Random and the prototype tie on observed
coverage, and every strategy reaches the same freshness signature on its first
launch. This study does not establish strategy superiority, distinct finding
quality, or the complete semantic-state method.

Evidence: [strategy-slice report](../experiments/main_strategy_comparison_thor_v1/FINAL_REPORT.md).

## Process-exit candidate

The `owned_process_exit_fallback_v1` action terminates the active external
producer during observed motion and requires a safe internal fallback. The
final non-formal qualification covers two mechanisms, three strategies, and
three rounds. All 18/18 qualification attempts were accepted, admissible,
physically valid, action-contract complete, and safe-fallback passing.

The candidate formal matrix contains 18 planned launches, passes dry-run and
mismatch checks, and has no formal ledger. It contributes zero launches to the
295 total. Under the v8 plan, readiness does not authorize execution; the
action must first be assessed as part of the common corpus and evaluation
contract.

Evidence: [process-exit preregistration](../experiments/main_process_exit_strategy_thor_v1/preregistration.md).

## Other completed evidence work

- Finding and consequence triage localizes the observed attitude-installation
  signatures but does not establish a source-level cause:
  [report](../experiments/posthoc_finding_consequence_triage_v1/FINAL_REPORT.md).
- Oracle ablation measures which contract components change detection:
  [report](../experiments/posthoc_oracle_ablation_v1/FINAL_REPORT.md).
- Threshold sensitivity records dependence on research-contract thresholds:
  [report](../experiments/posthoc_threshold_sensitivity_v1/FINAL_REPORT.md).
- Observer, physical-validity, and Dynamic readiness qualification is retained
  separately from formal denominators:
  [report](../experiments/stage_a2_runtime_qualification_v1/FINAL_REPORT.md).
- Four-way remains the qualified formal concurrency. A five-way trial was not
  promoted because it reduced clock margin and changed one matched timing-
  sensitive interpretation:
  [record](../experiments/concurrency_barrier_qualification/README.md).

## Available implementation

The repository currently contains:

- normalized event schemas and Runtime Route Instance fields;
- hash-chained collection and environment attestation;
- Evidence Admissibility Gate;
- Route, Freshness/Lineage, Successor, and Registration contracts;
- safety supervision, cleanup, attempt accounting, and batch barriers;
- locked sources and ARM64 Thor container/toolchain definitions;
- official, bounded-random timing, and prototype state-aware policies;
- qualified setpoint-stall and process-exit live backends;
- the v8 semantic-state schema, its deterministic offline extractor, and the
  digest-bound replay of that extractor over every retained admissible trace;
  and
- retained formal reports, compact evidence, and ledgers.

The repository does not yet contain:

- a live generator that consumes the full semantic state, rather than the
  narrower `route_active` / `motion_entered` prototype state;
- multi-action closed-loop sequence generation;
- the mechanism- and provenance-selected core corpus;
- deterministic and feedback-free main baselines under one common contract;
- a confirmed historical/natural/seeded benchmark;
- repeated campaign-level statistical evaluation; or
- full-stack seed extraction and representative finding replay.

## Historical evidence boundary

Earlier narrative work referred to Orin-era evidence, including a lifecycle
successor case. The current branch contains no source report, ledger, compact
evidence, or replayable artifact for that layer. The retained count for that
layer therefore remains zero. Such material can become background or a benchmark only
after its provenance and evidence are supplied independently.

## Semantic state extraction

The v8 state defined in [ROUTE_MODEL.md](ROUTE_MODEL.md) now has a tracked
schema, a deterministic extractor, and a read-only replay over the whole
retained corpus: 213 accepted attempts across the five closed studies.

- 213 / 213 attempts re-derive to an identical trajectory digest from an
  independent parse of the retained file;
- 213 / 213 are unchanged when every declared-mode field is removed and when it
  is replaced by an impossible value, so mode independence is measured rather
  than asserted;
- the derived state separates route epoch, authority owner, lifecycle progress
  and command freshness, reaching 191 distinct semantic states, 56 semantic
  edges, 9 lifecycle phases, 12 actions and 9 contract boundaries; and
- under reduced observation none of the 213 attempts retains command lineage or
  command freshness, and only the 8 health-loss attempts keep any contract
  boundary, because their activation rejection rides on a public fault event.

This is Stage 1 implementation and measurement work. It adds no formal launch,
no denominator, and no claim about PX4 behavior.

Evidence: [Stage 1 replay report](../experiments/stage1_semantic_state_replay_v1/FINAL_REPORT.md).

## Candidate action corpus

The Stage 2 inventory is available and machine-verified against the repository:
17 records over the two plan axes, 12 candidates that all have retained
evidence, and 5 gaps whose role stays undecided because no implementation and no
evidence exist for them. Every declared contract boundary is observed in that
candidate's own evidence.

The five gaps are communication delay or reconnect, operator or ground-station
takeover, concurrent external producers, producer restart after loss, and
induced failsafe takeover. Three axis pairs consequently have no evidence at
all.

A seven-action core selection is proposed on top of that inventory: six actions
that already exist as fixtures with retained evidence, plus one new action whose
legality depends on the outcome of an earlier action. Each precondition is a
predicate over the semantic state and was replayed against all 213 accepted
attempts; six are consistent with every retained firing and the seventh is
reported as unvalidated because it has no implementation.

The corpus is not signed. The generator cannot select an action today — it
chooses only a timing offset for a preconfigured action — so a corpus frozen
over that decision space would fix a null generation result by construction. The
signing conditions are recorded with the decision.

Evidence: [Stage 2 inventory report](../experiments/stage2_action_corpus_inventory_v1/FINAL_REPORT.md),
[conditional freeze](../experiments/stage2_core_corpus_freeze_v1/CONDITIONAL_FREEZE.md),
[precondition check](../experiments/stage2_core_corpus_freeze_v1/FINAL_REPORT.md).

## Active next step

No formal campaign is currently authorized. Work proceeds through the decision
gates in [EXPERIMENT_PLAN.md](EXPERIMENT_PLAN.md). Stage 1 extraction is
available and its exit checks are met, and the Stage 2 inventory is available
and unfrozen. The next decisions are the Stage 2 corpus freeze and the Stage 3
closed loop, which must consume the semantic state instead of the prototype
state. Then come baselines, ground truth and full-stack replay, and finally
pilot and preregistered repeated campaigns.

The preregistered process-exit matrix still verifies as launch-ready: its
dry-run resolves six pending cells and 18 planned launches against the attested
image, and it still has no formal ledger. Readiness remains separate from
authorization.

## Current claim boundary

The repository supports a bounded measurement and Motivation claim plus one
generation-feasibility slice. It does not support:

- a general method-effectiveness claim;
- random-versus-state-aware ranking;
- a process-exit formal result;
- a PX4 defect prevalence estimate;
- pooling independent study denominators; or
- generalization beyond the retained Thor SITL scope.
