# Post-hoc Threshold Sensitivity v1

## Scope and accounting

This is a read-only replay over all 151 frozen admissible Motivation traces: 131 primary and 20 supplemental. It does not modify the traces, formal evaluations, thresholds, ledgers, matrices, denominators, summaries, or reports. The frozen formal verdict remains the reported formal result.

The Full Oracle replay contains 171 Oracle instances. Eight preregistered activation-rejection instances have no transition request and are `NOT_APPLICABLE` to continuous route timing. The sensitivity denominator is therefore 163 transition instances from 143 traces. These are applicability exclusions, not missing trace inputs.

Every curve is one-factor-at-a-time. The selected threshold changes while all other clauses retain their frozen status. `curves.json` includes the fixed grid, every observed crossing, and maximal aggregate-count stability intervals. Missing observations remain `UNKNOWN`; no values are interpolated.

## Continuous observations

| Metric | Calculable / applicable | Median | P90 | Maximum | Frozen bound |
|---|---:|---:|---:|---:|---:|
| Maximum retained-command age | 163 / 163 | 133.052 ms | 5009.979 ms | 5064.351 ms | 200 ms |
| Route installation | 163 / 163 | 136.110 ms | 206.966 ms | 785.004 ms | 300 ms |
| Route revocation | 163 / 163 | 19.750 ms | 26.836 ms | 31.146 ms | 300 ms |
| Actuator-effect continuity gap | 163 / 163 | 199.951 ms | 200.185 ms | 800.277 ms | 250 ms |
| Completion-to-successor installation | 127 / 127 | 130.958 ms | 215.400 ms | 274.948 ms | 300 ms |
| Dynamic process exit to observed health loss | 8 / 8 | 1111.505 ms | 1234.642 ms | 1234.642 ms | none preregistered |
| Dynamic process exit to fallback trigger | 8 / 8 | 1112.179 ms | 1235.445 ms | 1235.445 ms | 1500 ms plan value |
| Dynamic process exit to complete fallback | 8 / 8 | 1153.391 ms | 1345.855 ms | 1345.855 ms | 1500 ms plan value |
| legacy_offboard process exit to fallback trigger | 8 / 8 | 1278.941 ms | 1444.857 ms | 1444.857 ms | 1500 ms plan value |
| legacy_offboard process exit to complete fallback | 8 / 8 | 1130.204 ms | 1286.780 ms | 1286.780 ms | 1500 ms plan value |
| legacy_offboard process exit to explicit proof-of-life loss | 0 / 8 | — | — | — | none preregistered |

The frozen normalized traces do not contain a distinct legacy_offboard proof-of-life-loss event. All eight such observations remain `UNKNOWN`; the analysis does not substitute a fallback trigger for the missing event. Dynamic External Mode health loss is evaluated only from its external-component health event and does not use `COM_OF_LOSS_T`.

## Frozen-bound observations and sensitivity

At the frozen research bounds, the continuous observations cross as follows: retained-command age 115 pass / 48 violation; installation 152 / 11; revocation 163 / 0; continuity 149 / 14; successor 127 / 0. These are per-instance threshold projections, not new formal verdicts and not independent defect counts.

Four command-age observations lie between the 200 ms frozen bound and the next 225 ms grid point. No installation, revocation, continuity, successor, or mechanism-specific fallback observation lies in the corresponding first grid step above its frozen bound. Across each full prespecified grid:

- Command age has 5 stable-pass, 40 stable-violation, and 118 threshold-dependent observations.
- Installation has 43 stable-pass and 120 threshold-dependent observations.
- Revocation has 163 stable-pass observations.
- Continuity has 28 stable-pass, 9 stable-violation, and 126 threshold-dependent observations.
- Successor has 36 stable-pass and 91 threshold-dependent observations.

The exact stability intervals and counts are in `curves.json`; reporting only one threshold would conceal this dependence. The four near-frozen command-age crossings are listed there with trace and transition identity.

## Interpretation boundary

The 200 ms freshness, 300 ms installation/revocation/successor, 250 ms continuity, and retained 1500 ms fallback plan values are research safety-contract thresholds in this analysis. Crossing one is not presented as a public PX4 specification violation. The curves neither revise the 94 PASS / 57 VIOLATION frozen formal result nor establish that the 57 trace-level violations are 57 independent software defects.

The input manifest records the digest of every frozen trace and plan plus the Oracle-ablation summary. Re-running the command below in a new output directory reproduces the generated JSON files without writing to frozen inputs:

```sh
python3 -m scripts.analysis.sensitivity \
  --root . \
  --output-root /tmp/posthoc-threshold-sensitivity-v1
```
