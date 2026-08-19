# Stage 1 Semantic State Replay v1

## Scope and paper role

This is a read-only replay of the v8 semantic-state extractor over every
retained admissible trace in the repository: 213 accepted attempts across five
independently closed studies. It belongs to the paper's Implementation section
and to the Stage 1 exit record in
[EXPERIMENT_PLAN.md](../../docs/EXPERIMENT_PLAN.md).

It modifies no plan, trace, evaluation, threshold, ledger, denominator, or
report. It creates no formal denominator and no new empirical claim about PX4.
It answers only whether the derived state is deterministic, mode-label
independent, and observably dependent on the tracked instrumentation.

## Inputs

| Study | Accepted attempts replayed |
| --- | ---: |
| `motivation-thor-v1` | 131 |
| `motivation-thor-remediation-v1` | 20 |
| `motivation-stage-a2-thor-v1` | 18 |
| `motivation-stage-a2-thor-remediation-v1` | 26 |
| `main-strategy-comparison-thor-v1` | 18 |
| Total | 213 |

Every attempt is selected from its own hash-verified study ledger, and each
attempt's retained plan and `closed.trace.jsonl` are digest-recorded in
`input-manifest.json`. The freshness bound is the `maximum_command_age_ns`
frozen in each attempt's own plan, not a value chosen by this analysis.

## Registered checks and results

| Check | Rule | Result |
| --- | --- | --- |
| Deterministic replay | re-parse the retained file and re-derive; trajectory digests must match | 213 / 213 |
| Mode-label independence | re-derive with every declared-mode field removed, and again with it replaced by an impossible sentinel; both digests must equal the original | 213 / 213 |
| Route-epoch distinction | at least one route reaches a second distinct epoch in the same trace | 175 / 213 attempts |
| Owner distinction | both internal and external authority owners are visited | met |
| Lifecycle progress | idle, activation requested, activated, executing, completed, replacing and terminal are all visited | met |
| Command freshness | both fresh and stale consumption are visited | met |

All six Stage 1 exit checks are met. `summary.json` records
`exit_criteria_met: true`, an empty `non_deterministic_attempts` list, and an
empty `mode_label_dependent_attempts` list.

Declared-mode fields are present in the evidence of 78 of the 213 attempts,
carried by `completion` events. Removing or corrupting them changes no derived
trajectory, so mode independence is a measured property of the extractor rather
than a claim about the evidence.

## Derived coverage over the retained corpus

- 191 distinct semantic states and 56 distinct semantic edges;
- 29 distinct final states;
- 9 of the 10 lifecycle phases (`registered` is not reached as a distinct
  phase because every traced registration occurs while an internal route is
  already executing);
- 12 distinct actions, including four fault classes and an explicit
  registration rejection; and
- 9 of the 10 contract boundaries.

Both rejection boundaries are exercised: `registration_rejected` in the 8
accepted capacity attempts and `activation_rejected` in the 8 accepted
health-loss attempts. Only `evidence_gap` is absent, which is expected because
a critical collection gap normally makes a trace inadmissible and so keeps it
out of an accepted corpus.

The rejection rules are the ones the Registration Contract Oracle already uses:
a `registration` event with `result_code` 2, and a `fault_detected` event whose
reason states a rejection. An earlier revision of this extractor looked for a
boolean rejection flag that real evidence never carries, which made both
boundaries unreachable. The defect was found while building the Stage 2
inventory and is fixed here.

Motion context is `unobserved` for all 213 attempts. The closed trace carries
no physical observation, and this analysis deliberately supplies no motion
samples rather than inferring a phase. Binding the retained Stage A2 physical
analysis into the extractor is separate work.

## Reduced-observation dependence

The reduced view keeps exactly the events that ordinary public interfaces and
host-side lifecycle records produce, and drops every event carrying
`raw_source_domain`, which is precisely what the tracked observability patches
emit.

| Property retained without the instrumentation | Attempts |
| --- | ---: |
| Command lineage observable | 0 / 213 |
| Command freshness observable | 0 / 213 |
| Any contract boundary observable | 8 / 213 |
| Final state identical to the full view | 1 / 213 |

Under reduced observation the derived state keeps only request, completion,
fault and terminal markers; route identity, epoch, owner, lineage and freshness
all collapse to explicit unknowns. The 8 attempts that keep a boundary are the
health-loss cells, whose `activation_rejected` marker rides on a public fault
event rather than on instrumented uORB evidence; registration rejection, by
contrast, is instrumented and is lost.

The single attempt whose final state matches is `fault-dynamic-health-loss-010`,
a health-loss cell whose full-view final state already has no route installed
and unknown freshness. That match is an absence agreeing with an absence, not
the reduced view recovering evidence.

This is the quantified instrumentation dependence the method requires. It says
the grey-box contract is load-bearing for this state; it does not say the
method would be undetectable through other instrumentation.

## Limitations

- The replay measures extraction, not generation. The live loop still consumes
  the narrower prototype state.
- Determinism is established for the retained evidence and the current
  extractor revision. It is not a proof for evidence shapes absent from this
  corpus.
- Coverage counts are derived from the retained corpus and depend on which
  cells those five studies happened to preregister. They are not a coverage
  claim about PX4 or about a future campaign.
- The reduced-observation split follows event provenance in the normalized
  trace. It approximates what a build without the observability patches would
  produce; it is not a re-run of such a build.

## Reproduction

```bash
python3 -m scripts.analysis.semantic_state_replay --root . --output-root <fresh dir>
```

The command refuses a non-empty output directory, refuses any study whose
ledger fails verification, and refuses an attempt whose retained plan or trace
is missing.
