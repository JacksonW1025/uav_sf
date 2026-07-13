# RAPTOR Full Campaign External Review Packet

Date: 2026-07-07

Repository: `github.com/JacksonW1025/uav_sf`

Purpose: this is the single Markdown file to send to an external AI reviewer. It summarizes the RAPTOR reintegration and full 2026-07-05 campaign evidence, states the current conclusion, and lists the important repository-relative files that should be inspected in the remote repository.

All paths below are relative to the repository root.

## Executive Verdict

The RAPTOR 2026-07-05 full review line completed. The current evidence does not support a confirmed RAPTOR primary bug.

The strongest claim supported by the artifacts is:

- Original clipped RAPTOR is now connected as a mc_nn-comparable SUT in the current campaign harness.
- The RAPTOR full route-A switch-severity campaign set completed.
- The controlled dense sweep completed with 120/120 valid evaluations, 0 invalid evaluations, and 0 strict S0-vs-S3 hits.
- The grid/guided/random search campaigns produced reportable relative-degradation candidates, but no confirmed primary bugs and no confirmed reportable findings.
- The anchor recheck and boundary runs did not produce a RAPTOR primary bug.

The honest conclusion is negative for the tested RAPTOR SUT: no confirmed strict classical-S0 versus RAPTOR-S3 catastrophic differential was found in this full pass. This does not prove RAPTOR is universally safe. It says the tested original RAPTOR, with its source-level input clipping preserved, did not reproduce the mc_nn route-A catastrophic finding under this harness and campaign set.

## Reviewer Questions

Please review whether the listed evidence supports these claims:

1. The RAPTOR campaign artifacts are complete enough to say the 2026-07-05 RAPTOR full pass finished.
2. The dense sweep result really rules out strict S0-vs-S3 hits over the controlled grid that was swept.
3. The search campaign reportable candidates are correctly treated as relative-degradation diagnostics rather than confirmed primary findings.
4. The runner errors in grid/guided/random campaigns are coverage limitations, not positive evidence for a RAPTOR primary bug.
5. The remaining threats are stated honestly, especially RAPTOR's preserved input clipping and the absence of an unclipped RAPTOR variant.

## Background

Earlier RAPTOR evidence was only a lightweight closeout. It found no confirmed primary bug, but it was not equivalent to the current mc_nn campaign harness. The 2026-07-05 reintegration work changed that: RAPTOR was added as a selectable SUT in the campaign/evaluation stack, with RAPTOR-specific runner dispatch, identity gating, metadata, and property comparison. The original RAPTOR input clipping was intentionally preserved.

Important background files:

- `docs/raptor_recon_2026-07-05.md`
- `docs/raptor_reintegration_smoke_2026-07-05.md`
- `docs/RAPTOR_closeout.md`
- `docs/PROJECT_NARRATIVE_CONTEXT_v8 (1).md`

Key caveat from the background: old RAPTOR "robust" evidence was a low-evidence null relative to the later mc_nn campaign. The current evidence is stronger because it uses the same style of route-A campaign harness, but it still tests original clipped RAPTOR, not an unclipped ablation.

## Harness And Method Summary

The comparison pairs a classical controller run with a selected neural SUT run under the same theta/task. For RAPTOR, the selected neural controller is `raptor`, not `mcnn`.

The primary catastrophic predicate is strict S0-vs-S3: decontaminated classical control-window severity S0 and neural/RAPTOR severity S3. Continuous property rho gaps are used for search quality and diagnostic relative degradation, but they are not enough by themselves to claim a primary catastrophic bug.

The campaign stack uses:

- `scripts/campaign_runner.py`
- `scripts/m2_map_elites.py`
- `scripts/property_fitness.py`
- `scripts/validity_automation.py`
- `scripts/run_switch_dense_sweep.py`

Relevant tests:

- `tests/test_campaign_runner.py`
- `tests/test_property_fitness.py`
- `tests/test_validity_automation.py`

Implementation changes relevant to review:

- SUT selection supports `mcnn` and `raptor`.
- `fitness_mode` is persisted through campaign config/resume/metadata.
- `absolute_severity` fitness exists as an RQ2 ablation mode, while the RAPTOR full campaign here used differential fitness.
- RAPTOR identity gating checks RAPTOR-specific status/input evidence and excludes `neural_control` topic confusion.
- The dense sweep script enumerates controlled route-A switch-severity axes and writes a structured summary.

## Full RAPTOR 2026-07-05 Result Set

### Dense Sweep

Run directory:

- `runs/campaigns/raptor_switch_severity_dense_sweep_20260705`

Important files:

- `runs/campaigns/raptor_switch_severity_dense_sweep_20260705/sweep_config.json`
- `runs/campaigns/raptor_switch_severity_dense_sweep_20260705/sweep_results.jsonl`
- `runs/campaigns/raptor_switch_severity_dense_sweep_20260705/summary.json`

Summary:

| field | value |
| --- | ---: |
| total points | 40 |
| total evals | 120 |
| valid evals | 120 |
| invalid evals | 0 |
| strict S0-vs-S3 hits | 0 |

Axis coverage:

| axis | points | evals | valid | invalid | strict S0-vs-S3 hits |
| --- | ---: | ---: | ---: | ---: | ---: |
| `attitude_deg` | 9 | 27 | 27 | 0 | 0 |
| `requested_rate_rad_s` | 9 | 27 | 27 | 0 | 0 |
| `wind_m_s` | 7 | 21 | 21 | 0 | 0 |
| `switch_delay_s` | 7 | 21 | 21 | 0 | 0 |
| `approach_phase_rad` | 8 | 24 | 24 | 0 | 0 |

Interpretation: this is the cleanest RAPTOR artifact in the set. It is a controlled sweep over the route-A switch-severity axes with no invalids and no strict catastrophic differential.

### Search Campaigns

Search campaign directories:

- `runs/campaigns/raptor_switch_severity_grid_0_20260705`
- `runs/campaigns/raptor_switch_severity_guided_0_20260705`
- `runs/campaigns/raptor_switch_severity_guided_1_20260705`
- `runs/campaigns/raptor_switch_severity_guided_2_20260705`
- `runs/campaigns/raptor_switch_severity_random_0_20260705`
- `runs/campaigns/raptor_switch_severity_random_1_20260705`
- `runs/campaigns/raptor_switch_severity_random_2_20260705`

Top-level summary:

| run | strategy | evals | runner errors | primary candidates | reportable candidates | strict S0-vs-S3 evals | relative degradation evals | confirmed primary | confirmed reportable | best relative degradation |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `raptor_switch_severity_grid_0_20260705` | grid | 120 | 19 | 0 | 13 | 0 | 13 | 0 | 0 | P2 gap=0.391215, e0022 |
| `raptor_switch_severity_guided_0_20260705` | guided | 120 | 28 | 0 | 18 | 0 | 18 | 0 | 0 | P2 gap=1.336, e0090 |
| `raptor_switch_severity_guided_1_20260705` | guided | 120 | 11 | 0 | 12 | 0 | 12 | 0 | 0 | P2 gap=0.668929, e0098 |
| `raptor_switch_severity_guided_2_20260705` | guided | 120 | 17 | 0 | 13 | 0 | 13 | 0 | 0 | P2 gap=0.747371, e0107 |
| `raptor_switch_severity_random_0_20260705` | random | 120 | 2 | 0 | 11 | 0 | 11 | 0 | 0 | P2 gap=0.752456, e0079 |
| `raptor_switch_severity_random_1_20260705` | random | 120 | 2 | 0 | 5 | 0 | 5 | 0 | 0 | P1 gap=0.0848477, e0047 |
| `raptor_switch_severity_random_2_20260705` | random | 120 | 4 | 0 | 10 | 0 | 10 | 0 | 0 | P2 gap=1.22238, e0052 |

Aggregate for the seven 120-eval search runs:

- Planned/evaluated: 840 evals.
- Runner errors: 83.
- Primary candidates: 0.
- Reportable relative-degradation candidates/evals: 82.
- Confirmed primary bugs: 0.
- Confirmed reportable findings: 0.
- Strict S0-vs-S3 evals: 0.

The reportable candidate count means there are property-level relative-degradation diagnostics worth inspecting. It does not mean a confirmed RAPTOR primary finding exists.

Important files for each search campaign:

- `summary.md`
- `metadata.json`
- `checkpoint.json`
- `evals.jsonl`
- `progress.jsonl`
- `archive.json`
- `validity_records.json`
- `theta_ulog_map.json`
- `primary_candidates.json`
- `reportable_candidates.json`
- `confirmed_primary_bugs.json`
- `confirmed_reportable_findings.json`

The most important candidate-detail files are:

- `runs/campaigns/raptor_switch_severity_guided_0_20260705/reportable_candidates.json`
- `runs/campaigns/raptor_switch_severity_random_2_20260705/reportable_candidates.json`
- `runs/campaigns/raptor_switch_severity_grid_0_20260705/reportable_candidates.json`

These contain the strongest relative-degradation cases, but their matching `confirmed_*` files are empty.

### Gate0 Stability

Run directory:

- `runs/campaigns/raptor_gate0_stability_20260705`

Important files:

- `runs/campaigns/raptor_gate0_stability_20260705/summary.md`
- `runs/campaigns/raptor_gate0_stability_20260705/reportable_candidates.json`
- `runs/campaigns/raptor_gate0_stability_20260705/confirmed_primary_bugs.json`
- `runs/campaigns/raptor_gate0_stability_20260705/confirmed_reportable_findings.json`
- `runs/campaigns/raptor_gate0_stability_20260705/evals.jsonl`
- `runs/campaigns/raptor_gate0_stability_20260705/validity_records.json`

Summary:

| field | value |
| --- | ---: |
| evals | 30 |
| runner errors | 1 |
| primary candidates | 0 |
| reportable candidates | 4 |
| strict S0-vs-S3 evals | 0 |
| relative degradation evals | 4 |
| confirmed primary bugs | 0 |
| confirmed reportable findings | 0 |

Interpretation: Gate0 did not expose a RAPTOR primary bug. It produced small relative-degradation diagnostics only.

### Anchor Recheck

Run directory:

- `runs/campaigns/raptor_gate0_anchor_recheck_20260705`

Important files:

- `runs/campaigns/raptor_gate0_anchor_recheck_20260705/anchor_plan.json`
- `runs/campaigns/raptor_gate0_anchor_recheck_20260705/anchor_results.jsonl`
- `runs/campaigns/raptor_gate0_anchor_recheck_20260705/summary.json`

Summary:

| field | value |
| --- | ---: |
| records | 8 |
| returncode 0 | 8 |
| identity passes | 8 |
| primary bugs | 0 |

Interpretation: the anchor recheck passed RAPTOR identity and did not show a primary bug.

### Anchor Boundary

Run directory:

- `runs/campaigns/raptor_gate0_anchor_boundary_20260705`

Important files:

- `runs/campaigns/raptor_gate0_anchor_boundary_20260705/boundary_plan.json`
- `runs/campaigns/raptor_gate0_anchor_boundary_20260705/boundary_results.jsonl`
- `runs/campaigns/raptor_gate0_anchor_boundary_20260705/summary.json`

Summary:

| anchor | attempts | valid | classical S0 | RAPTOR S0 | primary bugs |
| --- | ---: | ---: | ---: | ---: | ---: |
| pair4 | 6 | 6 | 4 | 6 | 0 |
| pair5 | 6 | 6 | 5 | 6 | 0 |

Interpretation: the boundary runs again did not produce a RAPTOR primary bug. RAPTOR stayed S0 in all 12 boundary attempts.

## Evidence Chain By Claim

### Claim A: RAPTOR was actually connected as the selected SUT

Evidence:

- `docs/raptor_reintegration_smoke_2026-07-05.md`
- `scripts/campaign_runner.py`
- `scripts/m2_map_elites.py`
- `scripts/validity_automation.py`
- `tests/test_campaign_runner.py`
- `tests/test_validity_automation.py`

Review target: confirm the SUT selector, RAPTOR runner dispatch, and RAPTOR identity gate are not just metadata changes. The smoke report states that real RAPTOR ULOGs passed identity in 8/8 evaluations.

### Claim B: The controlled dense sweep completed cleanly

Evidence:

- `runs/campaigns/raptor_switch_severity_dense_sweep_20260705/summary.json`
- `runs/campaigns/raptor_switch_severity_dense_sweep_20260705/sweep_results.jsonl`
- `runs/campaigns/raptor_switch_severity_dense_sweep_20260705/sweep_config.json`
- `scripts/run_switch_dense_sweep.py`

Review target: verify `total_evals=120`, `total_valid=120`, `total_invalid=0`, and `total_strict_s0_vs_s3=0`.

### Claim C: Search campaigns found relative-degradation candidates but no confirmed RAPTOR finding

Evidence:

- `runs/campaigns/raptor_switch_severity_*_20260705/summary.md`
- `runs/campaigns/raptor_switch_severity_*_20260705/reportable_candidates.json`
- `runs/campaigns/raptor_switch_severity_*_20260705/confirmed_primary_bugs.json`
- `runs/campaigns/raptor_switch_severity_*_20260705/confirmed_reportable_findings.json`
- `runs/campaigns/raptor_switch_severity_*_20260705/validity_records.json`

Review target: distinguish diagnostic relative degradation from confirmed findings. The summary files consistently show `primary_candidates: 0`, `strict_s0_vs_s3_evals: 0`, `confirmed_primary_bugs: 0`, and `confirmed_reportable_findings: 0`.

### Claim D: Runner errors are a limitation, not a positive bug result

Evidence:

- `runs/campaigns/raptor_switch_severity_*_20260705/summary.md`
- `runs/campaigns/raptor_switch_severity_*_20260705/progress.jsonl`
- `runs/campaigns/raptor_switch_severity_*_20260705/validity_records.json`
- `runs/campaigns/raptor_switch_severity_*_20260705/evals.jsonl`

Review target: inspect whether rc=2/rc=3 task failures were excluded from candidate/confirmed bug accounting. The current interpretation is that they reduce coverage in some search runs but are not evidence of a RAPTOR-specific catastrophic differential.

## Important File Path Index

### Send-this-file report

- `docs/raptor_external_ai_review_2026-07-07.md`

### Background reports

- `docs/raptor_recon_2026-07-05.md`
- `docs/raptor_reintegration_smoke_2026-07-05.md`
- `docs/RAPTOR_closeout.md`
- `docs/PROJECT_NARRATIVE_CONTEXT_v8 (1).md`
- `docs/rq2_archive_reanalysis_20260705.md`
- `docs/rq2_archive_reanalysis_20260705.json`

### Dense sweep artifacts

- `runs/campaigns/raptor_switch_severity_dense_sweep_20260705/sweep_config.json`
- `runs/campaigns/raptor_switch_severity_dense_sweep_20260705/sweep_results.jsonl`
- `runs/campaigns/raptor_switch_severity_dense_sweep_20260705/summary.json`

### Search summaries

- `runs/campaigns/raptor_switch_severity_grid_0_20260705/summary.md`
- `runs/campaigns/raptor_switch_severity_guided_0_20260705/summary.md`
- `runs/campaigns/raptor_switch_severity_guided_1_20260705/summary.md`
- `runs/campaigns/raptor_switch_severity_guided_2_20260705/summary.md`
- `runs/campaigns/raptor_switch_severity_random_0_20260705/summary.md`
- `runs/campaigns/raptor_switch_severity_random_1_20260705/summary.md`
- `runs/campaigns/raptor_switch_severity_random_2_20260705/summary.md`

### Gate and anchor summaries

- `runs/campaigns/raptor_gate0_stability_20260705/summary.md`
- `runs/campaigns/raptor_gate0_anchor_recheck_20260705/summary.json`
- `runs/campaigns/raptor_gate0_anchor_boundary_20260705/summary.json`

### Candidate and confirmation artifacts

For each search or stability directory, inspect:

- `primary_candidates.json`
- `reportable_candidates.json`
- `confirmed_primary_bugs.json`
- `confirmed_reportable_findings.json`
- `validity_records.json`
- `evals.jsonl`
- `theta_ulog_map.json`
- `theta/*.json`

The relevant directories are:

- `runs/campaigns/raptor_gate0_stability_20260705`
- `runs/campaigns/raptor_switch_severity_grid_0_20260705`
- `runs/campaigns/raptor_switch_severity_guided_0_20260705`
- `runs/campaigns/raptor_switch_severity_guided_1_20260705`
- `runs/campaigns/raptor_switch_severity_guided_2_20260705`
- `runs/campaigns/raptor_switch_severity_random_0_20260705`
- `runs/campaigns/raptor_switch_severity_random_1_20260705`
- `runs/campaigns/raptor_switch_severity_random_2_20260705`

### Code and tests that make the results interpretable

- `scripts/campaign_runner.py`
- `scripts/m2_map_elites.py`
- `scripts/property_fitness.py`
- `scripts/validity_automation.py`
- `scripts/run_switch_dense_sweep.py`
- `scripts/rq2_archive_reanalysis.py`
- `tests/test_campaign_runner.py`
- `tests/test_property_fitness.py`
- `tests/test_validity_automation.py`
- `tests/test_rq2_archive_reanalysis.py`

## Files Deliberately Not Required For First-Pass Review

The top-level run artifacts and `theta/*.json` files above are enough for remote review of the conclusion. The per-evaluation `evals/` subdirectories, `.ulg` flight logs, and raw task logs are much larger and should only be pulled if a reviewer wants to replay or inspect one specific theta.

The report path index includes JSONL and candidate files, but not the full per-eval raw directories.

## Known Limitations And Threats

1. RAPTOR input clipping was preserved. This is the original RAPTOR SUT behavior, but it means the result cannot answer whether unclipped RAPTOR would fail.
2. Search campaigns had runner errors. They are excluded from confirmed finding accounting, but they reduce coverage for those search arms.
3. The dense sweep is controlled and clean, but it covers the predefined axis grid, not the entire continuous route-A space.
4. Relative degradation candidates are real diagnostics, but the current confirmed-finding files are empty.
5. Old RAPTOR closeout artifacts are lower evidence than the 2026-07-05 full pass and should not be over-weighted.

## Bottom Line For External Review

The remote repository should contain this report plus the listed top-level run artifacts. Based on the current evidence, the defensible conclusion is:

Original clipped RAPTOR completed the 2026-07-05 full route-A switch-severity review without a confirmed primary bug. The dense sweep is clean. Search produced relative-degradation candidates, including P2 gaps above 1.0 in some runs, but none escalated to confirmed primary or confirmed reportable findings. The main residual risks are coverage gaps from runner errors, finite grid scope, and the fact that clipped RAPTOR was tested rather than an unclipped ablation.
