# Campaign runner summary

run_dir: `runs/campaigns/raptor_switch_severity_random_1_20260705`
strategy: random
evals: 120
budget: 120
completed: True
runner_errors: 2
classical_usable: 22
archive_bins: 9
primary_candidates: 0
reportable_property_candidates: 5
strict_s0_vs_s3_evals: 0
strict_differential_evals: 0
relative_degradation_evals: 5
best_relative_degradation: P1 gap=0.0848477 tag=raptor_switch_severity_random_1_20260705_e0047
confirmed_primary_bugs: 0
confirmed_reportable_findings: 0
checkpoint: `runs/campaigns/raptor_switch_severity_random_1_20260705/checkpoint.json`

## progress
| eval | best quality | archive bins | QD-score | relative evals | source | error |
|---:|---:|---:|---:|---:|---|---|
| 0 | -1e+09 | 0 | 0 | 0 | random_baseline |  |
| 60 | 0.10112 | 7 | 0.28706 | 4 | random_baseline |  |
| 119 | 0.138449 | 9 | 0.598091 | 5 | random_baseline |  |

## best elites
- switching:rp_4:wind_0: quality=0.138449 theta=`runs/campaigns/raptor_switch_severity_random_1_20260705/theta/raptor_switch_severity_random_1_20260705_e0070.json`
- switching:rp_4:wind_4: quality=0.133095 theta=`runs/campaigns/raptor_switch_severity_random_1_20260705/theta/raptor_switch_severity_random_1_20260705_e0094.json`
- switching:rp_3:wind_0: quality=0.10112 theta=`runs/campaigns/raptor_switch_severity_random_1_20260705/theta/raptor_switch_severity_random_1_20260705_e0002.json`
- switching:rp_4:wind_2: quality=0.0848477 theta=`runs/campaigns/raptor_switch_severity_random_1_20260705/theta/raptor_switch_severity_random_1_20260705_e0047.json`
- switching:rp_3:wind_1: quality=0.0810412 theta=`runs/campaigns/raptor_switch_severity_random_1_20260705/theta/raptor_switch_severity_random_1_20260705_e0109.json`
- switching:rp_3:wind_3: quality=0.0413673 theta=`runs/campaigns/raptor_switch_severity_random_1_20260705/theta/raptor_switch_severity_random_1_20260705_e0093.json`
- switching:rp_4:wind_3: quality=0.0181701 theta=`runs/campaigns/raptor_switch_severity_random_1_20260705/theta/raptor_switch_severity_random_1_20260705_e0097.json`
- switching:rp_3:wind_2: quality=-0.00480255 theta=`runs/campaigns/raptor_switch_severity_random_1_20260705/theta/raptor_switch_severity_random_1_20260705_e0090.json`
- switching:rp_4:wind_1: quality=-0.012515 theta=`runs/campaigns/raptor_switch_severity_random_1_20260705/theta/raptor_switch_severity_random_1_20260705_e0037.json`
