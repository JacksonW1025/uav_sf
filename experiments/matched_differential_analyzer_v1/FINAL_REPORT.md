# Matched Differential Analyzer v1

## Implemented contract

The analyzer treats mechanism as the primary treatment and supports `legacy_offboard`, Dynamic External Mode, and Mode Executor arms. A block receives an identity derived from its profile and every declared match field; each derived pair receives a separate identity derived from the block and two mechanisms.

The match gate distinguishes:

- `UNMATCHED`: abstract task, setpoint level, fault meaning, successor meaning, or fallback meaning differs; a profile is semantically inconsistent; fewer than two distinct mechanisms are present; or the declared block identity is invalid.
- `PARTIALLY_MATCHED`: a seed, action timing, CPU set, load, observer, environment, or common software field differs. The prespecified action-time tolerance is 20 ms.
- `FULLY_MATCHED`: all semantic and operational match checks pass.

`FULLY_MATCHED` alone is insufficient for paired estimation. Every arm must also have `ADMISSIBLE` evidence. Excluded attempts and structured mismatch reasons remain in the block result. Mode Executor may enter a block only by satisfying the same explicit semantic fields; a lifecycle-only wrapper cannot be forced into an unrelated data-path comparison.

## Differential outputs

For each eligible pair, the analyzer reports route installation, revocation, retained-command age, lineage, normalized owner correctness, successor, fallback, physical outcome, evidence completeness, a paired correctness vector, paired latency differences, and a divergence signature. Across multiple eligible blocks it reports the paired mean, median, range, and standardized within-pair effect when estimable.

A divergence produces `DIFFERENTIAL_DIVERGENCE` only in the differential layer. The saved correctness verdicts are carried through unchanged. Unmatched, partially matched, or evidence-inadmissible blocks never enter an effect estimate.

## Frozen Motivation smoke test

The read-only smoke test examined all 151 frozen admissible Motivation traces. All 151 are recorded as `UNMATCHED` descriptive observations with reason `NO_PREREGISTERED_MATCHED_BLOCK`; none is retroactively grouped by cell name or route. Consequently, this current analysis contains:

- formal matched blocks: 0;
- eligible paired blocks: 0;
- paired effects: 0;
- differential findings from real matched execution: 0.

This is the correct result for the existing corpus because its seed and cell assignments were not preregistered as common matched blocks. It is not evidence that the mechanisms are equal or different.

## Validation and future use

Synthetic tests cover full, partial, unmatched, duplicate-mechanism, inadmissible-evidence, divergence, and multi-block effect-size cases. Those tests validate software behavior only and are not experiment findings.

`future-formal-block.example.json` shows the required future matrix shape. Its attempt identities are explicitly `NOT_EXECUTED`, its observations are unknown, and both Evidence Gates are inadmissible. It cannot enter paired estimation until replaced by registered, observed attempts.

The current smoke test is reproduced with:

```sh
python3 -m scripts.analysis.matched_differential \
  --root . \
  --output-root /tmp/matched-differential-analyzer-v1 \
  --motivation-smoke
```
