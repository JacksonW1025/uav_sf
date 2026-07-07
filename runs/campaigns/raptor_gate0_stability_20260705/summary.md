# Campaign runner summary

run_dir: `runs/campaigns/raptor_gate0_stability_20260705`
strategy: guided
evals: 30
budget: 30
completed: True
runner_errors: 1
classical_usable: 12
archive_bins: 6
primary_candidates: 0
reportable_property_candidates: 4
strict_s0_vs_s3_evals: 0
strict_differential_evals: 0
relative_degradation_evals: 4
best_relative_degradation: P1 gap=0.0965182 tag=raptor_gate0_stability_20260705_e0010
confirmed_primary_bugs: 0
confirmed_reportable_findings: 0
checkpoint: `runs/campaigns/raptor_gate0_stability_20260705/checkpoint.json`

## progress
| eval | best quality | archive bins | QD-score | relative evals | source | error |
|---:|---:|---:|---:|---:|---|---|
| 0 | -1e+09 | 0 | 0 | 1 | bootstrap_random |  |
| 15 | 0.00255074 | 3 | 0.00255074 | 2 | elite_mutation |  |
| 29 | 0.183289 | 6 | 0.316204 | 4 | elite_mutation |  |

## best elites
- switching:rp_4:wind_3: quality=0.183289 theta=`runs/campaigns/raptor_gate0_stability_20260705/theta/raptor_gate0_stability_20260705_e0025.json`
- switching:rp_3:wind_1: quality=0.0727415 theta=`runs/campaigns/raptor_gate0_stability_20260705/theta/raptor_gate0_stability_20260705_e0019.json`
- switching:rp_4:wind_2: quality=0.047278 theta=`runs/campaigns/raptor_gate0_stability_20260705/theta/raptor_gate0_stability_20260705_e0029.json`
- switching:rp_3:wind_4: quality=0.0103441 theta=`runs/campaigns/raptor_gate0_stability_20260705/theta/raptor_gate0_stability_20260705_e0022.json`
- switching:rp_3:wind_3: quality=0.00255074 theta=`runs/campaigns/raptor_gate0_stability_20260705/theta/raptor_gate0_stability_20260705_e0011.json`
- switching:rp_3:wind_2: quality=-0.000643357 theta=`runs/campaigns/raptor_gate0_stability_20260705/theta/raptor_gate0_stability_20260705_e0012.json`
