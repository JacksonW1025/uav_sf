# Campaign runner summary

run_dir: `runs/campaigns/raptor_switch_severity_random_2_20260705`
strategy: random
evals: 120
budget: 120
completed: True
runner_errors: 4
classical_usable: 19
archive_bins: 8
primary_candidates: 0
reportable_property_candidates: 10
strict_s0_vs_s3_evals: 0
strict_differential_evals: 0
relative_degradation_evals: 10
best_relative_degradation: P2 gap=1.22238 tag=raptor_switch_severity_random_2_20260705_e0052
confirmed_primary_bugs: 0
confirmed_reportable_findings: 0
checkpoint: `runs/campaigns/raptor_switch_severity_random_2_20260705/checkpoint.json`

## progress
| eval | best quality | archive bins | QD-score | relative evals | source | error |
|---:|---:|---:|---:|---:|---|---|
| 0 | -1e+09 | 0 | 0 | 0 | random_baseline |  |
| 60 | 1.22238 | 3 | 1.26727 | 6 | random_baseline |  |
| 119 | 1.22238 | 8 | 1.79481 | 10 | random_baseline |  |

## best elites
- switching:rp_4:wind_4: quality=1.22238 theta=`runs/campaigns/raptor_switch_severity_random_2_20260705/theta/raptor_switch_severity_random_2_20260705_e0052.json`
- switching:rp_3:wind_0: quality=0.148589 theta=`runs/campaigns/raptor_switch_severity_random_2_20260705/theta/raptor_switch_severity_random_2_20260705_e0116.json`
- switching:rp_4:wind_0: quality=0.146403 theta=`runs/campaigns/raptor_switch_severity_random_2_20260705/theta/raptor_switch_severity_random_2_20260705_e0117.json`
- switching:rp_3:wind_4: quality=0.144993 theta=`runs/campaigns/raptor_switch_severity_random_2_20260705/theta/raptor_switch_severity_random_2_20260705_e0086.json`
- switching:rp_4:wind_3: quality=0.0896438 theta=`runs/campaigns/raptor_switch_severity_random_2_20260705/theta/raptor_switch_severity_random_2_20260705_e0096.json`
- switching:rp_3:wind_2: quality=0.0259248 theta=`runs/campaigns/raptor_switch_severity_random_2_20260705/theta/raptor_switch_severity_random_2_20260705_e0106.json`
- switching:rp_3:wind_3: quality=0.0126152 theta=`runs/campaigns/raptor_switch_severity_random_2_20260705/theta/raptor_switch_severity_random_2_20260705_e0049.json`
- switching:rp_4:wind_1: quality=0.00425983 theta=`runs/campaigns/raptor_switch_severity_random_2_20260705/theta/raptor_switch_severity_random_2_20260705_e0092.json`
