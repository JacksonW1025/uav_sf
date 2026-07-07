# Campaign runner summary

run_dir: `runs/campaigns/raptor_switch_severity_guided_0_20260705`
strategy: guided
evals: 120
budget: 120
completed: True
runner_errors: 28
classical_usable: 73
archive_bins: 10
primary_candidates: 0
reportable_property_candidates: 18
strict_s0_vs_s3_evals: 0
strict_differential_evals: 0
relative_degradation_evals: 18
best_relative_degradation: P2 gap=1.336 tag=raptor_switch_severity_guided_0_20260705_e0090
confirmed_primary_bugs: 0
confirmed_reportable_findings: 0
checkpoint: `runs/campaigns/raptor_switch_severity_guided_0_20260705/checkpoint.json`

## progress
| eval | best quality | archive bins | QD-score | relative evals | source | error |
|---:|---:|---:|---:|---:|---|---|
| 0 | -1e+09 | 0 | 0 | 0 | bootstrap_random |  |
| 60 | 0.751904 | 10 | 1.97465 | 10 | elite_mutation |  |
| 119 | 1.336 | 10 | 2.99909 | 18 | elite_mutation | RuntimeError: task node failed rc=3 for classical |

## best elites
- switching:rp_4:wind_4: quality=1.336 theta=`runs/campaigns/raptor_switch_severity_guided_0_20260705/theta/raptor_switch_severity_guided_0_20260705_e0090.json`
- switching:rp_4:wind_1: quality=0.615006 theta=`runs/campaigns/raptor_switch_severity_guided_0_20260705/theta/raptor_switch_severity_guided_0_20260705_e0017.json`
- switching:rp_3:wind_1: quality=0.174441 theta=`runs/campaigns/raptor_switch_severity_guided_0_20260705/theta/raptor_switch_severity_guided_0_20260705_e0037.json`
- switching:rp_4:wind_0: quality=0.149574 theta=`runs/campaigns/raptor_switch_severity_guided_0_20260705/theta/raptor_switch_severity_guided_0_20260705_e0047.json`
- switching:rp_3:wind_0: quality=0.138978 theta=`runs/campaigns/raptor_switch_severity_guided_0_20260705/theta/raptor_switch_severity_guided_0_20260705_e0083.json`
- switching:rp_3:wind_3: quality=0.12872 theta=`runs/campaigns/raptor_switch_severity_guided_0_20260705/theta/raptor_switch_severity_guided_0_20260705_e0094.json`
- switching:rp_4:wind_2: quality=0.12425 theta=`runs/campaigns/raptor_switch_severity_guided_0_20260705/theta/raptor_switch_severity_guided_0_20260705_e0020.json`
- switching:rp_3:wind_4: quality=0.11947 theta=`runs/campaigns/raptor_switch_severity_guided_0_20260705/theta/raptor_switch_severity_guided_0_20260705_e0106.json`
- switching:rp_3:wind_2: quality=0.113525 theta=`runs/campaigns/raptor_switch_severity_guided_0_20260705/theta/raptor_switch_severity_guided_0_20260705_e0088.json`
- switching:rp_4:wind_3: quality=0.099122 theta=`runs/campaigns/raptor_switch_severity_guided_0_20260705/theta/raptor_switch_severity_guided_0_20260705_e0040.json`
