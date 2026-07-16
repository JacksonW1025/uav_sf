# M2 MAP-Elites run summary

run_dir: `docs/validity_automation_mock_20260627`
evals: 3
runner_errors: 0
classical_usable: 3
archive_bins: 1
primary_candidates: 3
confirmed_primary_bugs: 1

## progress
| eval | best quality | archive bins | QD-score | source | parent quality |
|---:|---:|---:|---:|---|---:|
| 0 | 1.34528 | 1 | 1.34528 | bootstrap_random | n/a |
| 1 | 1.34528 | 1 | 1.34528 | elite_mutation | 1.34528 |
| 2 | 1.36449 | 1 | 1.36449 | elite_mutation | 1.34528 |

## best elites
- physics_mismatch:high: quality=1.36449 quadrant=property_differential theta=`docs/validity_automation_mock_20260627/theta/validity_automation_mock_20260627_e0002.json`

## primary candidates
- validity_automation_mock_20260627_e0000: quality=1.34528 theta=`docs/validity_automation_mock_20260627/theta/validity_automation_mock_20260627_e0000.json` compare=`docs/validity_automation_mock_20260627/evals/validity_automation_mock_20260627_e0000/m1_diff_validity_automation_mock_20260627_e0000.json`
- validity_automation_mock_20260627_e0001: quality=1.34528 theta=`docs/validity_automation_mock_20260627/theta/validity_automation_mock_20260627_e0001.json` compare=`docs/validity_automation_mock_20260627/evals/validity_automation_mock_20260627_e0001/m1_diff_validity_automation_mock_20260627_e0001.json`
- validity_automation_mock_20260627_e0002: quality=1.36449 theta=`docs/validity_automation_mock_20260627/theta/validity_automation_mock_20260627_e0002.json` compare=`docs/validity_automation_mock_20260627/evals/validity_automation_mock_20260627_e0002/m1_diff_validity_automation_mock_20260627_e0002.json`

## confirmed
- validity_automation_mock_20260627_e0002: 2 repeats passed
