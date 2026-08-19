# Stage 2 Action and Workload Corpus Inventory v1

## Scope and paper role

This is the Stage 2 inventory required by
[EXPERIMENT_PLAN.md](../../docs/EXPERIMENT_PLAN.md) before any core corpus is
frozen. It belongs to the paper's Implementation and Evaluation-setup sections.

It is deliberately **not a frozen corpus**. `inventory.json` records
`frozen: false`, and the plan is explicit that the number and identity of
actions are outputs of the analysis rather than assumptions. This artifact adds
no formal launch, no denominator, and no claim about PX4 behavior.

## Method

Each candidate is declared once, in
[scripts/corpus/action_inventory.py](../../scripts/corpus/action_inventory.py),
and must survive verification against the repository before it can appear in
the artifact:

- every provenance path must exist;
- every referenced matrix cell must exist in that study's matrix;
- every live backend must be a wired action contract;
- every declared contract boundary must exist in the semantic-state model;
- a gap may not claim matrix cells, and a candidate must have at least one.

Evidence is joined, never declared. Launch and accepted counts come from the
study ledgers; observed contract boundaries come from the Stage 1 semantic-state
replay. The build refuses to run at all if that replay artifact is absent, which
keeps the plan's stage order enforced rather than assumed.

## Inventory

17 records: 12 candidates and 5 gaps. Every candidate has retained evidence.

| Action | Phase | Mechanism | Role | Launches / accepted |
| --- | --- | --- | --- | ---: |
| `register_external_mode` | registration | nominal | realism validation | 11 / 10 |
| `registration_capacity_rejection` | registration | rejection | benchmark | 9 / 8 |
| `request_external_activation` | activation | nominal | realism validation | 11 / 10 |
| `activation_rejection_after_health_loss` | activation | health loss | benchmark | 10 / 8 |
| `owned_setpoint_stall_healthy` | execution | setpoint or callback stall | benchmark | 30 / 30 |
| `setpoint_kind_variation` | execution | nominal | discovery | 26 / 26 |
| `nominal_completion_release` | completion | nominal | realism validation | 20 / 20 |
| `mode_executor_completion` | completion | nominal | realism validation | 5 / 5 |
| `adjacent_land_request_near_completion` | replacement | adjacent authority request | discovery | 50 / 30 |
| `owned_process_exit_fallback` | fallback | process loss/restart | benchmark | 18 / 16 |
| `route_re_entry_through_hold` | re-entry | nominal | benchmark | 10 / 10 |
| `route_re_entry_through_rtl` | re-entry | nominal | benchmark | 30 / 10 |

Counts are per candidate across all of its cells, not per study, and they are
not additive across candidates: one attempt exercises several candidates at
once. They are reachability and provenance evidence, not a denominator.

Two counts carry information on their own. `route_re_entry_through_rtl` shows
30 launches for 10 accepted because its primary cell reached its launch cap with
no accepted evidence and an independent remediation supplied the measurement;
it is the worked example of an unreachable fixture obligation.
`adjacent_land_request_near_completion` shows 50 launches for 30 accepted across
its three timing buckets.

## Gaps

Five mechanisms named by the method action grammar have no implementation and
no evidence, so their role stays `undecided`:

| Gap | Phase | Why it is not yet a candidate |
| --- | --- | --- |
| `communication_delay_or_reconnect` | execution | needs a controlled transport delay with a recorded applied schedule, and evidence separating the delay from scheduler jitter |
| `manual_or_gcs_takeover` | replacement | no operator or ground-station channel exists; only the adjacent internal request is implemented |
| `concurrent_external_producers` | replacement | the capacity cell registers extra components but never lets a second producer contend for an installed route |
| `producer_restart_after_exit` | fallback | only the loss is implemented; reclaiming authority after a loss has no fixture |
| `failsafe_takeover` | fallback | no failsafe condition is deliberately induced, and it would need its own safety qualification |

Three axis pairs therefore have candidates but no evidence at all:
execution × communication delay, replacement × manual or failsafe takeover, and
fallback × manual or failsafe takeover.

## Boundary consistency

Every contract boundary declared by a candidate is observed in that candidate's
retained evidence; `declared_not_observed` is empty. Two model boundaries are
declared by no candidate:

- `target_partially_installed`, which is a derived observation of an
  installation in progress rather than something an action aims at; and
- `evidence_gap`, which marks a critical collection gap and normally makes a
  trace inadmissible.

## A defect this inventory found

Building the join surfaced a defect in the Stage 1 extractor. It looked for a
boolean rejection flag on `registration` events, which real evidence never
carries, and it never recorded activation rejection at all. Both rejection
boundaries were therefore unreachable, and the first Stage 1 report wrongly
attributed their absence to the corpus. The extractor now uses the same rules as
the Registration Contract Oracle, the Stage 1 artifact was regenerated, and its
report records the correction. The affected cells are
`fault-dynamic-registration-capacity` and `fault-dynamic-health-loss`, each with
8 accepted attempts.

## Limitations

- Roles are a research judgment recorded with a stated basis. Where the basis is
  an unexplained observation, the role is `discovery`; where there is no
  evidence at all, it is `undecided`. None of them is a finding.
- Reachability is established for the locked Thor SITL environment and the
  retained fixtures only.
- The inventory covers the two declared axes. It does not yet rank candidates,
  assign budgets, or select the minimal representative subset; that selection is
  the freeze step, and it is deliberately not performed here.
- Real full-stack events receive high investigation priority under the plan.
  None is included yet, because no full-stack trace is retained in this branch.

## Reproduction

```bash
python3 -m scripts.corpus.action_inventory --root . --output-root <fresh dir>
```

The command refuses a non-empty output directory, refuses a candidate whose
provenance, cell, backend or boundary cannot be verified, and refuses to run
without the Stage 1 replay artifact.
