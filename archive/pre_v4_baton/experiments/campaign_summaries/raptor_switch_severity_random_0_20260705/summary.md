# Campaign runner summary

run_dir: `runs/campaigns/raptor_switch_severity_random_0_20260705`
strategy: random
evals: 120
budget: 120
completed: True
runner_errors: 2
classical_usable: 19
archive_bins: 8
primary_candidates: 0
reportable_property_candidates: 11
strict_s0_vs_s3_evals: 0
strict_differential_evals: 0
relative_degradation_evals: 11
best_relative_degradation: P2 gap=0.752456 tag=raptor_switch_severity_random_0_20260705_e0079
confirmed_primary_bugs: 0
confirmed_reportable_findings: 0
checkpoint: `runs/campaigns/raptor_switch_severity_random_0_20260705/checkpoint.json`

## progress
| eval | best quality | archive bins | QD-score | relative evals | source | error |
|---:|---:|---:|---:|---:|---|---|
| 0 | -1e+09 | 0 | 0 | 0 | random_baseline |  |
| 60 | 0.0919927 | 7 | 0.225201 | 1 | random_baseline |  |
| 119 | 0.131847 | 8 | 0.432904 | 11 | random_baseline |  |

## best elites
- switching:rp_3:wind_1: quality=0.131847 theta=`runs/campaigns/raptor_switch_severity_random_0_20260705/theta/raptor_switch_severity_random_0_20260705_e0093.json`
- switching:rp_3:wind_2: quality=0.123435 theta=`runs/campaigns/raptor_switch_severity_random_0_20260705/theta/raptor_switch_severity_random_0_20260705_e0099.json`
- switching:rp_3:wind_0: quality=0.0919927 theta=`runs/campaigns/raptor_switch_severity_random_0_20260705/theta/raptor_switch_severity_random_0_20260705_e0009.json`
- switching:rp_4:wind_1: quality=0.0686089 theta=`runs/campaigns/raptor_switch_severity_random_0_20260705/theta/raptor_switch_severity_random_0_20260705_e0051.json`
- switching:rp_3:wind_4: quality=0.0151406 theta=`runs/campaigns/raptor_switch_severity_random_0_20260705/theta/raptor_switch_severity_random_0_20260705_e0050.json`
- switching:rp_4:wind_0: quality=0.0018795 theta=`runs/campaigns/raptor_switch_severity_random_0_20260705/theta/raptor_switch_severity_random_0_20260705_e0041.json`
- switching:rp_4:wind_3: quality=-0.00724249 theta=`runs/campaigns/raptor_switch_severity_random_0_20260705/theta/raptor_switch_severity_random_0_20260705_e0062.json`
- switching:rp_4:wind_2: quality=-0.0273104 theta=`runs/campaigns/raptor_switch_severity_random_0_20260705/theta/raptor_switch_severity_random_0_20260705_e0022.json`
