# Current status

Last V8 repository audit: 2026-08-18. The research direction is defined in
[NEW_NARRATIVE_v8.md](NEW_NARRATIVE_v8.md). This file records completed facts
and the current checkout boundary.

## Executive status

```text
Repository consolidation (Stage 0): COMPLETE
Next gate: observation/evidence provenance contract
Retained formal launches across separate Thor studies: 295
Retained earlier-device results: 0
Motivation and measurement foundation: complete with bounded claims
Full semantic-state generation method: not implemented
Active V8 flight image / runner / formal matrix: none
Formal campaign currently running or authorized: none
```

The 295 launches are a repository total, not one pooled experiment. Each study
retains its own identity, matrix, ledger, thresholds, and denominator.

## Formal study accounting

| Study | Formal launches | Accepted/admissible evidence | Result boundary |
| --- | ---: | ---: | --- |
| Stage A1 primary | 180 | 131 | 75 PASS, 56 VIOLATION; two invalid-plan cells did not reach target |
| Stage A1 remediation | 20 | 20 | 19 PASS, 1 VIOLATION under an independent identity |
| Stage A2 primary | 51 | 18 | Permanently `MEASUREMENT_INSUFFICIENT`; 31 observability rejection and 2 inconclusive |
| Stage A2 remediation | 26 | 26 | 10 normal PASS, 16 deliberate freshness VIOLATION |
| Timing/feedback feasibility slice | 18 | 18 | 18 deliberate freshness VIOLATION; bounded prototype evidence only |

## Stage A1 Motivation

The primary study closed 180 launches: 131 accepted, 20 observability
rejections, 28 timeouts, and one environment failure. The separately
preregistered remediation closed 20/20 new launches. Across the two identities,
151 accepted/admissible traces contain 94 overall PASS and 57 overall
VIOLATION.

These results support bounded claims that mode/terminal outcomes do not prove a
complete authority handoff, route and freshness are separate dimensions,
successor installation and timing order are separate facts, route names require
runtime instance identity, and measurement failures must remain separate from
SUT results. They are not a defect rate.

Evidence:

- [Stage A1 primary report](../experiments/motivation_thor_v1/FINAL_REPORT.md)
- [Stage A1 remediation report](../experiments/motivation_thor_remediation_v1/FINAL_REPORT.md)

## Physical-validity audit

A digest-bound post-hoc audit found 12 of the 151 Stage A1 admissible traces did
not rise more than 0.08 m above their local-position origin: 3 PASS and 9
VIOLATION. Frozen results are unchanged, but physical interpretation is limited.

This establishes a V8 requirement: trace admissibility alone does not establish
physical task validity.

Evidence: [physical-validity report](../experiments/posthoc_physical_execution_validity_v1/FINAL_REPORT.md).

## Stage A2 realism bridge

The Stage A2 primary study closed 51 launches and remains
`MEASUREMENT_INSUFFICIENT` because a command-subject clock-closure problem
prevented three cells from reaching target. The independent remediation changed
the evidence-closure rule and public takeoff obligation under a new identity,
then closed 26/26 accepted/admissible launches:

- 10 normal traces PASS;
- 16 deliberate healthy-stall traces violate freshness only;
- median post-stall motion is approximately 1.01--1.03 m; and
- median task-progress shortfall is approximately 0.46--0.47 m.

The result supports bounded physical interpretability, not mechanism
superiority, flyaway, real-flight danger, or a general PX4 defect.

Evidence:

- [Stage A2 primary report](../experiments/motivation_stage_a2_thor_v1/FINAL_REPORT.md)
- [Stage A2 remediation report](../experiments/motivation_stage_a2_thor_remediation_v1/FINAL_REPORT.md)
- [Stage A2 runtime qualification](../experiments/stage_a2_runtime_qualification_v1/FINAL_REPORT.md)

## Timing/feedback feasibility evidence

The retained setpoint-stall slice closed 18/18 formal launches across two
mechanisms and three frozen timing policies. All attempts were accepted,
admissible, physically valid deliberate freshness violations. The fixed policy
covered one timing bin; bounded random and the prototype feedback policy each
covered three and exposed the same signature on their first launch.

The frozen label `official_sequence` denotes a fixed policy inside that study;
it is not a provenance-backed official PX4 scenario baseline. The slice proves
only that bounded live feedback plumbing executed. It does not establish the
V8 method, a strategy ranking, distinct finding quality, or campaign-level
statistics.

Evidence: [timing-slice report](../experiments/main_strategy_comparison_thor_v1/FINAL_REPORT.md).

## Other retained evidence support

- [Oracle ablation](../experiments/posthoc_oracle_ablation_v1/FINAL_REPORT.md)
  records component sensitivity without creating new findings.
- [Threshold sensitivity](../experiments/posthoc_threshold_sensitivity_v1/FINAL_REPORT.md)
  records dependence on research thresholds.
- [Finding/consequence triage](../experiments/posthoc_finding_consequence_triage_v1/FINAL_REPORT.md)
  localizes exposures but does not establish source-level cause.
- [Concurrency qualification](../experiments/concurrency_barrier_qualification/README.md)
  records a four-way result for the old workload. It does not authorize any
  concurrency for a new V8 runtime.

## Current tracked implementation

Retained partial primitives include:

- route-event and Runtime Route Instance skeletons;
- raw hash-chained collection, ULog field extraction, and clock fitting;
- Route, Freshness/Lineage, Successor, and Registration Oracle components;
- append-only accounting, safety/cleanup, artifact hashing, isolation, and
  physical-takeoff helpers; and
- in-scope Stage A2 and ROS/PX4 workload components.

The checkout intentionally does not contain:

- an active observation/stimulus patch or flight image;
- a normalized V8 trace closure with field provenance;
- a combined trace/environment/physical admissibility Gate;
- V8 plan, campaign, episode, action-sequence, result, or finding schemas;
- a complete semantic-state extractor;
- multi-action closed-loop generation or four comparable methods;
- an active runner, evaluator, formal matrix, or flight command;
- a frozen benchmark or confirmation state machine; or
- full-stack seed extraction and representative consequence replay.

See [V8_REPOSITORY_AUDIT.md](V8_REPOSITORY_AUDIT.md) for retained/deleted
inventory and known conflicts.

## Historical evidence boundary

Earlier narrative work mentioned prior-device evidence, but this checkout has
no source report, ledger, compact evidence, or replayable artifact for it. Its
retained count remains zero. It may enter a future benchmark only after
independent provenance and evidence are supplied.

## Active next step

No flight or formal campaign is authorized. Follow the
[Chinese step-by-step plan](EXPERIMENT_PLAN.zh-CN.md), beginning with the
observation/evidence provenance contract. The current repository validator
proves Stage 0 boundary consistency only.

## Current claim boundary

The repository supports a bounded Thor SITL Motivation/measurement claim plus
one feedback-feasibility slice. It does not support method effectiveness,
random-versus-guided ranking, PX4 defect prevalence, pooled denominators,
full-stack consequences, or generalization beyond the retained scope.
