# Campaign runner summary

run_dir: `runs/campaigns/raptor_switch_severity_grid_0_20260705`
strategy: grid
evals: 120
budget: 120
completed: True
runner_errors: 19
classical_usable: 27
archive_bins: 7
primary_candidates: 0
reportable_property_candidates: 13
strict_s0_vs_s3_evals: 0
strict_differential_evals: 0
relative_degradation_evals: 13
best_relative_degradation: P2 gap=0.391215 tag=raptor_switch_severity_grid_0_20260705_e0022
confirmed_primary_bugs: 0
confirmed_reportable_findings: 0
checkpoint: `runs/campaigns/raptor_switch_severity_grid_0_20260705/checkpoint.json`

## progress
| eval | best quality | archive bins | QD-score | relative evals | source | error |
|---:|---:|---:|---:|---:|---|---|
| 0 | -1e+09 | 0 | 0 | 1 | grid_baseline |  |
| 60 | -1e+09 | 0 | 0 | 10 | grid_baseline |  |
| 119 | 0.190815 | 7 | 0.725858 | 13 | grid_baseline | RuntimeError: task node failed rc=3 for classical |

## best elites
- switching:rp_3:wind_1: quality=0.190815 theta=`runs/campaigns/raptor_switch_severity_grid_0_20260705/theta/raptor_switch_severity_grid_0_20260705_e0083.json`
- switching:rp_3:wind_2: quality=0.163329 theta=`runs/campaigns/raptor_switch_severity_grid_0_20260705/theta/raptor_switch_severity_grid_0_20260705_e0085.json`
- switching:rp_3:wind_4: quality=0.124558 theta=`runs/campaigns/raptor_switch_severity_grid_0_20260705/theta/raptor_switch_severity_grid_0_20260705_e0096.json`
- switching:rp_3:wind_3: quality=0.10757 theta=`runs/campaigns/raptor_switch_severity_grid_0_20260705/theta/raptor_switch_severity_grid_0_20260705_e0090.json`
- switching:rp_3:wind_0: quality=0.089142 theta=`runs/campaigns/raptor_switch_severity_grid_0_20260705/theta/raptor_switch_severity_grid_0_20260705_e0077.json`
- switching:rp_4:wind_1: quality=0.0504436 theta=`runs/campaigns/raptor_switch_severity_grid_0_20260705/theta/raptor_switch_severity_grid_0_20260705_e0105.json`
- switching:rp_4:wind_3: quality=-0.019796 theta=`runs/campaigns/raptor_switch_severity_grid_0_20260705/theta/raptor_switch_severity_grid_0_20260705_e0118.json`
