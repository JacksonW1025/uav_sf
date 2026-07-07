# Campaign runner summary

run_dir: `runs/campaigns/raptor_switch_severity_guided_2_20260705`
strategy: guided
evals: 120
budget: 120
completed: True
runner_errors: 17
classical_usable: 63
archive_bins: 10
primary_candidates: 0
reportable_property_candidates: 13
strict_s0_vs_s3_evals: 0
strict_differential_evals: 0
relative_degradation_evals: 13
best_relative_degradation: P2 gap=0.747371 tag=raptor_switch_severity_guided_2_20260705_e0107
confirmed_primary_bugs: 0
confirmed_reportable_findings: 0
checkpoint: `runs/campaigns/raptor_switch_severity_guided_2_20260705/checkpoint.json`

## progress
| eval | best quality | archive bins | QD-score | relative evals | source | error |
|---:|---:|---:|---:|---:|---|---|
| 0 | -1e+09 | 0 | 0 | 0 | bootstrap_random |  |
| 60 | 0.351526 | 10 | 0.859745 | 5 | elite_mutation |  |
| 119 | 0.747371 | 10 | 1.72379 | 13 | elite_mutation |  |

## best elites
- switching:rp_4:wind_3: quality=0.747371 theta=`runs/campaigns/raptor_switch_severity_guided_2_20260705/theta/raptor_switch_severity_guided_2_20260705_e0107.json`
- switching:rp_4:wind_0: quality=0.351526 theta=`runs/campaigns/raptor_switch_severity_guided_2_20260705/theta/raptor_switch_severity_guided_2_20260705_e0031.json`
- switching:rp_4:wind_2: quality=0.137076 theta=`runs/campaigns/raptor_switch_severity_guided_2_20260705/theta/raptor_switch_severity_guided_2_20260705_e0075.json`
- switching:rp_3:wind_1: quality=0.120238 theta=`runs/campaigns/raptor_switch_severity_guided_2_20260705/theta/raptor_switch_severity_guided_2_20260705_e0026.json`
- switching:rp_3:wind_4: quality=0.11589 theta=`runs/campaigns/raptor_switch_severity_guided_2_20260705/theta/raptor_switch_severity_guided_2_20260705_e0045.json`
- switching:rp_4:wind_1: quality=0.106779 theta=`runs/campaigns/raptor_switch_severity_guided_2_20260705/theta/raptor_switch_severity_guided_2_20260705_e0093.json`
- switching:rp_3:wind_0: quality=0.0748952 theta=`runs/campaigns/raptor_switch_severity_guided_2_20260705/theta/raptor_switch_severity_guided_2_20260705_e0017.json`
- switching:rp_3:wind_3: quality=0.0383555 theta=`runs/campaigns/raptor_switch_severity_guided_2_20260705/theta/raptor_switch_severity_guided_2_20260705_e0058.json`
- switching:rp_3:wind_2: quality=0.0200857 theta=`runs/campaigns/raptor_switch_severity_guided_2_20260705/theta/raptor_switch_severity_guided_2_20260705_e0014.json`
- switching:rp_4:wind_4: quality=0.0115751 theta=`runs/campaigns/raptor_switch_severity_guided_2_20260705/theta/raptor_switch_severity_guided_2_20260705_e0028.json`
