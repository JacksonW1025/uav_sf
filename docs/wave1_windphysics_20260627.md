# Wave-1 wind+physics campaign

Scope: steady-wind-physics, target properties P4/P6/P7, speed factor 1.25, N=1 sequential SITL.
Labels are separated into weak candidate, strict absolute differential, and relative degradation differential. primary_bug is reserved for strict differentials only.

## Headline
- P7 trigger-property confirmations: 2/12 at >=2/3 repeats, 0/12 at 3/3 repeats.
- Legacy confirmation passed all 12 P7-trigger candidates via any target property, mostly P4/P6; that is not P7 confirmation.
- Strict primary bugs after relabeling: 0.
- Wave-1 P7 conclusion: distributional high-stress tail, not deterministic or robustly reproduced P7 degradation. The confirmation-seed variance is shared/comparable between classical and neural (pooled neural/classical P7 variance ratio 1.401).
- The 199/198 relative-eval counts are coverage/signal counts, not finding counts; P4 dominates them.

## Run Summary
| arm | evals | usable | errors | bins | QD | primary_bug evals | relative evals | P7 confirmed >=2/3 | P7 confirmed 3/3 | legacy confirmations | max gap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| guided | 200 | 199 | 1 | 8 | 5.251 | 0 | 199 | 1 | 0 | 6/6 | 0.9163 |
| random | 200 | 198 | 2 | 7 | 4.79 | 0 | 198 | 1 | 0 | 6/6 | 1.038 |

## Relative Degradation Distribution
Criterion: neural rho > 0, classical rho >= margin_c, and classical-minus-neural gap >= the property reproduction margin.
| property | valid gaps | relative flags | median gap | p90 gap | max gap | min neural rho |
|---|---:|---:|---:|---:|---:|---:|
| P4 | 397 | 397 | 0.1891 | 0.2077 | 0.2239 | 0.455 |
| P6 | 397 | 258 | 0.04937 | 0.097 | 0.2698 | 0.008836 |
| P7 | 397 | 51 | 0.01347 | 0.5152 | 1.038 | -0.1229 |

- P4 is an architecture baseline fact, not a finding count: 397/397 (100%) evals flag it, but the gap is narrow (median 0.1891, p90 0.2077, max 0.2239).
- P6 is a medium degradation band: 258/397 relative flags, median gap 0.04937, p90 0.097, max 0.2698.
- P7 is sparse but large in the single-draw tail: 51/397 (13%) relative flags, p90 gap 0.5152, max gap 1.038. This is a distributional tail signal, not a stable per-scenario degradation claim.

## Trigger-Property Confirmation Reanalysis
Legacy confirmation records used an any-target-property repeat match. Rejudgment below requires the same triggering property to repeat.
| trigger property | legacy trigger candidates | property-confirmed >=2/3 | property-confirmed 3/3 |
|---|---:|---:|---:|
| P4 | 12 | 12 | 12 |
| P6 | 10 | 10 | 10 |
| P7 | 12 | 2 | 0 |
| total candidate-property pairs | 34 | 24 | 22 |

### P7 Trigger Candidates
P7 gap repeats count confirmation seeds with P7 gap >= 0.4484874426. P7 relative repeats use the full relative-degradation predicate for P7; in this dataset the two counts match.
- P7 repeats recomputation: 9/12 candidates are 0/3, 1/12 are 1/3, 2/12 are 2/3, and 0/12 are 3/3.
- P7 gap-repeat count and P7 relative-repeat count mismatches: 0. The old P7-repeat column is therefore not a report-field bug for these data.
| arm | tag | wind | physics | P7 gap | classical rho | neural rho | margin | P7 gap repeats | P7 relative repeats | P7 >=2/3 | P7 3/3 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| random | `wave1_windphysics_random_20260627_e0117` | high | high | 1.038 | 1.257 | 0.219 | 0.4485 | 0/3 | 0/3 | no | no |
| random | `wave1_windphysics_random_20260627_e0055` | high | mid | 0.9358 | 1.252 | 0.3163 | 0.4485 | 0/3 | 0/3 | no | no |
| guided | `wave1_windphysics_guided_20260627_e0030` | high | mid | 0.9163 | 1.015 | 0.09887 | 0.4485 | 0/3 | 0/3 | no | no |
| random | `wave1_windphysics_random_20260627_e0150` | high | high | 0.9145 | 1.335 | 0.4202 | 0.4485 | 0/3 | 0/3 | no | no |
| guided | `wave1_windphysics_guided_20260627_e0134` | high | mid | 0.8994 | 1.079 | 0.1798 | 0.4485 | 1/3 | 1/3 | no | no |
| random | `wave1_windphysics_random_20260627_e0187` | high | high | 0.8737 | 1.463 | 0.5894 | 0.4485 | 0/3 | 0/3 | no | no |
| guided | `wave1_windphysics_guided_20260627_e0097` | high | low | 0.8064 | 1.148 | 0.3417 | 0.4485 | 0/3 | 0/3 | no | no |
| guided | `wave1_windphysics_guided_20260627_e0148` | high | high | 0.8033 | 1.134 | 0.3307 | 0.4485 | 0/3 | 0/3 | no | no |
| guided | `wave1_windphysics_guided_20260627_e0072` | mid | high | 0.8023 | 1.332 | 0.5298 | 0.4485 | 0/3 | 0/3 | no | no |
| guided | `wave1_windphysics_guided_20260627_e0159` | high | mid | 0.7828 | 1.318 | 0.5348 | 0.4485 | 2/3 | 2/3 | yes | no |
| random | `wave1_windphysics_random_20260627_e0111` | mid | mid | 0.7662 | 0.9143 | 0.1481 | 0.4485 | 0/3 | 0/3 | no | no |
| random | `wave1_windphysics_random_20260627_e0048` | high | mid | 0.7614 | 0.9628 | 0.2014 | 0.4485 | 2/3 | 2/3 | yes | no |

### P7 Confirmation-Seed Variance
- P7 jitter margin source: `scripts/validity_automation.py` uses P7 jitter band 0.2242437213, the max of fixed-theta serial pairwise ranges classical=0.2242437213 and mcnn=0.1979852921; the reproduction margin is 2x = 0.4484874426.
- Across the 12 P7-trigger candidates' confirmation seeds, neural P7 variance is not much larger than classical: mean variance neural 0.02465 vs classical 0.02409; pooled variance neural 0.04728 vs classical 0.03376 (ratio 1.401, median per-candidate ratio 0.7204).

| arm | tag | P7 repeats | classical P7 var | neural P7 var | neural/classical var |
|---|---|---:|---:|---:|---:|
| random | `wave1_windphysics_random_20260627_e0117` | 0/3 | 0.002563 | 0.0003953 | 0.1542 |
| random | `wave1_windphysics_random_20260627_e0055` | 0/3 | 0.01066 | 0.003808 | 0.3572 |
| guided | `wave1_windphysics_guided_20260627_e0030` | 0/3 | 0.03773 | 0.02986 | 0.7914 |
| random | `wave1_windphysics_random_20260627_e0150` | 0/3 | 0.009089 | 0.05179 | 5.698 |
| guided | `wave1_windphysics_guided_20260627_e0134` | 1/3 | 0.004701 | 0.07681 | 16.34 |
| random | `wave1_windphysics_random_20260627_e0187` | 0/3 | 0.0004338 | 0.001763 | 4.064 |
| guided | `wave1_windphysics_guided_20260627_e0097` | 0/3 | 0.06424 | 0.007224 | 0.1124 |
| guided | `wave1_windphysics_guided_20260627_e0148` | 0/3 | 0.01464 | 0.006782 | 0.4631 |
| guided | `wave1_windphysics_guided_20260627_e0072` | 0/3 | 0.0816 | 0.0829 | 1.016 |
| guided | `wave1_windphysics_guided_20260627_e0159` | 2/3 | 0.04833 | 0.01567 | 0.3242 |
| random | `wave1_windphysics_random_20260627_e0111` | 0/3 | 0.007103 | 0.004613 | 0.6494 |
| random | `wave1_windphysics_random_20260627_e0048` | 2/3 | 0.007966 | 0.01415 | 1.777 |

## RQ3: wind x physics degradation map
Cells show eval count, P7 relative-degradation count, max target-property gap, and minimum P7 neural rho. These are extreme-value single-draw summaries, not cell means or stable degradation estimates.

### Guided
| wind / physics | low | mid | high |
|---|---|---|---|
| low | n=0 | n=14; P7=0; gap=0.221; min_P7=0.6778 | n=15; P7=0; gap=0.3722; min_P7=0.3695 |
| mid | n=10; P7=2; gap=0.6076; min_P7=0.586 | n=29; P7=5; gap=0.7221; min_P7=0.2146 | n=41; P7=5; gap=0.8023; min_P7=0.3435 |
| high | n=15; P7=3; gap=0.8064; min_P7=0.1737 | n=37; P7=9; gap=0.9163; min_P7=0.09887 | n=39; P7=11; gap=0.8033; min_P7=0.1278 |

### Random
| wind / physics | low | mid | high |
|---|---|---|---|
| low | n=0 | n=18; P7=1; gap=0.6613; min_P7=0.6156 | n=41; P7=0; gap=0.4366; min_P7=0.617 |
| mid | n=1; P7=0; gap=0.2917; min_P7=0.8104 | n=19; P7=2; gap=0.7662; min_P7=0.1481 | n=49; P7=2; gap=0.6607; min_P7=0.25 |
| high | n=0 | n=20; P7=4; gap=0.9358; min_P7=-0.1229 | n=52; P7=7; gap=1.038; min_P7=-0.04428 |

## C3: guided vs random
| arm | evals | usable | errors | bins | QD | primary_bug evals | relative evals | P7 confirmed >=2/3 | P7 confirmed 3/3 | legacy confirmations | max gap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| guided | 200 | 199 | 1 | 8 | 5.251 | 0 | 199 | 1 | 0 | 6/6 | 0.9163 |
| random | 200 | 198 | 2 | 7 | 4.79 | 0 | 198 | 1 | 0 | 6/6 | 1.038 |

- Guided has a small illumination edge: QD 5.251 vs 4.79, archive bins 8 vs 7.
- Random still found the strongest single cell: max gap 1.038 vs guided 0.9163.
- Trigger-property P7 counts are tied at the >=2/3 level: guided 1 vs random 1. This is not a guided-search rout; the wave-1 target is common enough that random also reaches it. A stronger C3 claim belongs to rarer wave-2 objectives.

## Strict-negative boundary
- Strict absolute differentials found in wind+physics scope: 0.
- Random high-stress cells pushed neural P7 rho just below zero, but not through the jitter margin:
  - random `wave1_windphysics_random_20260627_e0019` (high/mid): classical rho 0.5822, neural rho -0.1229, gap 0.705; strict line neural <= -0.4485.
  - random `wave1_windphysics_random_20260627_e0058` (high/high): classical rho 0.7065, neural rho -0.04428, gap 0.7508; strict line neural <= -0.4485.
- Extreme corner check: P7 classical rho 0.8027, neural rho 0.3024, gap 0.5004, repro margin 0.4485; neural stayed above the absolute violation line.
- Interpretation: wave-1 supports relative degradation, not absolute violation, in this subspace.

## Validity
- Guided mcnn identity confirmed evals: 199/200.
- Random mcnn identity confirmed evals: 198/200.
- Confirmed-record sources: guided `confirmed_primary_bugs.json (legacy reportable-relative records)`, random `confirmed_primary_bugs.json (legacy reportable-relative records)`.
- Decontamination and identity gates are applied by campaign_runner before scoring; failed gates are recorded as returncode/error and excluded from quality.
