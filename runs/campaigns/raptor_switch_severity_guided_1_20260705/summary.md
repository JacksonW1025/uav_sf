# Campaign runner summary

run_dir: `runs/campaigns/raptor_switch_severity_guided_1_20260705`
strategy: guided
evals: 120
budget: 120
completed: True
runner_errors: 11
classical_usable: 76
archive_bins: 10
primary_candidates: 0
reportable_property_candidates: 12
strict_s0_vs_s3_evals: 0
strict_differential_evals: 0
relative_degradation_evals: 12
best_relative_degradation: P2 gap=0.668929 tag=raptor_switch_severity_guided_1_20260705_e0098
confirmed_primary_bugs: 0
confirmed_reportable_findings: 0
checkpoint: `runs/campaigns/raptor_switch_severity_guided_1_20260705/checkpoint.json`

## progress
| eval | best quality | archive bins | QD-score | relative evals | source | error |
|---:|---:|---:|---:|---:|---|---|
| 0 | -1e+09 | 0 | 0 | 0 | bootstrap_random |  |
| 60 | 0.264445 | 9 | 0.758603 | 6 | elite_mutation |  |
| 119 | 0.668929 | 10 | 1.54982 | 12 | elite_mutation |  |

## best elites
- switching:rp_4:wind_3: quality=0.668929 theta=`runs/campaigns/raptor_switch_severity_guided_1_20260705/theta/raptor_switch_severity_guided_1_20260705_e0098.json`
- switching:rp_4:wind_4: quality=0.264445 theta=`runs/campaigns/raptor_switch_severity_guided_1_20260705/theta/raptor_switch_severity_guided_1_20260705_e0039.json`
- switching:rp_3:wind_1: quality=0.137873 theta=`runs/campaigns/raptor_switch_severity_guided_1_20260705/theta/raptor_switch_severity_guided_1_20260705_e0099.json`
- switching:rp_4:wind_2: quality=0.108302 theta=`runs/campaigns/raptor_switch_severity_guided_1_20260705/theta/raptor_switch_severity_guided_1_20260705_e0058.json`
- switching:rp_4:wind_0: quality=0.102736 theta=`runs/campaigns/raptor_switch_severity_guided_1_20260705/theta/raptor_switch_severity_guided_1_20260705_e0035.json`
- switching:rp_4:wind_1: quality=0.0938886 theta=`runs/campaigns/raptor_switch_severity_guided_1_20260705/theta/raptor_switch_severity_guided_1_20260705_e0114.json`
- switching:rp_3:wind_0: quality=0.0754612 theta=`runs/campaigns/raptor_switch_severity_guided_1_20260705/theta/raptor_switch_severity_guided_1_20260705_e0025.json`
- switching:rp_3:wind_4: quality=0.0544932 theta=`runs/campaigns/raptor_switch_severity_guided_1_20260705/theta/raptor_switch_severity_guided_1_20260705_e0112.json`
- switching:rp_3:wind_2: quality=0.0266046 theta=`runs/campaigns/raptor_switch_severity_guided_1_20260705/theta/raptor_switch_severity_guided_1_20260705_e0087.json`
- switching:rp_3:wind_3: quality=0.0170854 theta=`runs/campaigns/raptor_switch_severity_guided_1_20260705/theta/raptor_switch_severity_guided_1_20260705_e0109.json`
