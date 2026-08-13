# Post-hoc Oracle Ablation Report

## Status and boundary

This analysis replayed all 151 frozen admissible Motivation traces without
changing a trace, plan, evaluation, threshold, ledger, matrix, denominator,
summary, or formal report. It is a same-trace post-hoc analysis, not a new
formal campaign and not a measurement of defect prevalence.

The replay evaluated five views:

1. the frozen formal verdict;
2. declared mode transition only;
3. landed/disarmed terminal outcome only;
4. `SAFUZZ_PUBLISHED_MODEL_ADAPTATION`;
5. the post-hoc Full Oracle, including independent evaluation of every
   matching repeated transition request.

The SaFUZZ adaptation uses only application state, declared mode, failsafe,
human-mode request, mission completion, and terminal observations. It does not
use route epoch, registration/activation identity, owner, command age, or
controller/allocator/writer lineage. It is an adaptation of the published
observation model, not a complete SaFUZZ reproduction, and it does not compare
generation or search effectiveness.

## Frozen inputs

| Input | Count or SHA-256 |
| --- | ---: |
| Primary admissible traces | 131 |
| Supplemental admissible traces | 20 |
| Combined traces | 151 |
| Primary matrix | `f22af8ea7e211223d9a8cb9059e34d035078555de23626324b8b6b6fb05781a1` |
| Primary ledger | `3558dba3180c1bfc9bbdfdab0e7b80c7a18da593dbb283ea36c34b65b39beb2a` |
| Supplemental matrix | `e53c4aaacf22e651145e49ce4be0659f4d36493a77d3b5fb59a1fb5540f08e1a` |
| Supplemental ledger | `99ef1259f47ff0443c9a21908719ee91dca2d8d05acacee85d2485f254f3f9ad` |

The input manifest records the digest of every plan, closed trace, and frozen
evaluation. Twenty traces contain two matching transition requests; the
remaining 131 contain one. The post-hoc evaluator checked all 171 transition
instances.

## Results

| Layer | PASS | VIOLATION | INCONCLUSIVE |
| --- | ---: | ---: | ---: |
| Frozen formal | 94 | 57 | 0 |
| Mode only | 143 | 0 | 8 |
| Terminal only | 151 | 0 | 0 |
| SaFUZZ published-model adaptation | 143 | 0 | 8 |
| Post-hoc Full Oracle | 94 | 57 | 0 |

The eight inconclusive mode/SaFUZZ cases are planned rejection cases for which
these observation models cannot establish why activation did not occur. They
are not converted to PASS from absence.

All 57 Full-Oracle violation traces were PASS under the terminal-only view.
They were also PASS under mode-only and the SaFUZZ adaptation. These are
`relative_missed_finding` observations with the Full Oracle as the comparison
reference. They are not labelled false negatives because this replay does not
provide independent ground truth for every finding.

The post-hoc and frozen top-level verdicts agree for all 151 traces. This zero
compatibility delta preserves the formal report while still fixing the replay
logic so that every repeated request receives its own Route, Freshness,
Lineage, Ownership, Completion, and Successor evaluation.

## Finding signatures and classification

The 63 violation clauses form five observation-signature clusters:

| Clause signature | Trace-level clauses |
| --- | ---: |
| Freshness bound | 41 |
| Installation bound | 11 |
| Continuity bound | 3 |
| Adjacent-request timing | 4 |
| Adjacent-request order | 4 |

These are signature clusters, not five proven root causes and not independent
software defect counts. A trace may contribute more than one clause. The
smallest observed representative trace for each signature is recorded in
`summary.json`; “smallest” refers only to retained event count and is not a
claim of experimental minimization.

Conservative semantic classification produced:

- public-spec-grounded clauses: 0;
- research-safety-contract clauses: 63;
- safety-relevant exposure classifications: 63;
- software/diagnostic anomaly classifications: 0;
- threshold-sensitive anomaly classifications: 63;
- possible experiment/Oracle artifact classifications: 0.

Zero in a class means this offline corpus and its registered plans did not
establish that class. In particular, a threshold violation is not promoted to
a public specification violation without a versioned public contract.

## Observation cost

| Layer | Fields | Stages | Mean observed events per trace |
| --- | ---: | ---: | ---: |
| Terminal only | 3 | 1 | 1.000 |
| Mode only | 3 | 1 | 6.272 |
| SaFUZZ adaptation | 7 | 3 | 9.172 |
| Full Oracle | 12 | 6 | 935.338 |

The event counts are descriptive observation volume, not runtime overhead.
Instrumentation overhead requires a separate qualification with and without
the observation patch.

## What this establishes

The replay establishes that the published observation predicates represented
by mode, failsafe, mission progression, and terminal outcome do not directly
contain the route identity, freshness, owner, or complete installation
evidence used by the Full Oracle. In this corpus, those simpler views accepted
57 traces on which the Full Oracle reported a registered safety-contract
violation.

It does not establish that SaFUZZ cannot be extended, that its generator would
miss the same executions, or that every Full-Oracle clause is a confirmed SUT
defect. The frozen corpus has no issue-specific ground-truth labels, so issue
localization is reported as not evaluated rather than inferred from symptoms.

## Reproduction

Primary command:

```bash
python3 -m scripts.analysis.oracle_ablation \
  --root . \
  --output-root experiments/posthoc_oracle_ablation_v1
```

The writer refuses to overwrite existing results. A verification run should
use a fresh directory and compare the three generated files:

```bash
verification_root="$(mktemp -d /tmp/uav-oracle-ablation-XXXXXX)"
python3 -m scripts.analysis.oracle_ablation \
  --root . \
  --output-root "$verification_root"
cmp experiments/posthoc_oracle_ablation_v1/input-manifest.json \
  "$verification_root/input-manifest.json"
cmp experiments/posthoc_oracle_ablation_v1/per-trace.jsonl \
  "$verification_root/per-trace.jsonl"
cmp experiments/posthoc_oracle_ablation_v1/summary.json \
  "$verification_root/summary.json"
```

Machine-readable results are in `per-trace.jsonl`, `summary.json`, and
`input-manifest.json`. The exact decision rules and paper identity are in
`analysis-plan.json`.
