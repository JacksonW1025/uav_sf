# uav_sf

This repository contains the PX4 SITL harness, controller overlays, and experiment artifacts for scenario fuzzing of learned UAV flight controllers.

The project tests learned low-level controllers against a tuned classical controller under matched scenarios. The core oracle is differential: report only cases where the classical controller remains safe and the learned controller becomes unsafe.

The authoritative project state is `docs/PROJECT_NARRATIVE_CONTEXT_v8 (1).md` (Narrative v8, rev. 2026-07-07b). It supersedes v7 and the older RAPTOR/M0/M1/M2 handoff material. Treat earlier narrative docs as history or supporting evidence unless V8 explicitly cites them.

## Current State

- The headline finding is a robust switch-transient differential failure in PX4 `mc_nn_control`: mode-23 handoff states where classical control gives S0 clean recovery while `mc_nn_control` reaches S3 loss of control/tumble. Anchor pairs 1/2/4 reproduce 3/3; pair 5 is an 8/9 probabilistic boundary anchor.
- The switch-severity campaign is complete for RQ1/RQ2/RQ3: guided search produced 179 primary findings and about 10 confirmed cells; guided improves hit rate, archive density, and consistency, but not the count of 3/3 confirmed bugs versus random. Controlled dense sweeps show a high-dimensional, non-monotonic boundary with rate holes, delay holes, and high-wind recovery.
- The boundary is deliberately narrow: multi-policy P1-P7 reanalysis, wind+physics wave-1, and state-contamination wave-2 are clean or diagnostic negatives. The robust differential failure is pinned to catastrophic P1/P2 switch transients, not steady non-switch axes or independent gradual behavior-policy degradation.
- RAPTOR is now a completed second-SUT contrast. The full original clipped RAPTOR campaign is a clean negative: dense sweep 120/120 valid with 0 strict findings, seven-arm search 840 evals with 0 confirmed primary, gate/anchor checks negative, and about 926 successful evals with 0 S3/S4 loss-of-control events.
- RAPTOR's negative result supports oracle discrimination and harness external validity. It does not support learned-specificity; the learned-specific claim is carried only by the `mc_nn_control` versus classical comparison.
- The unclipped RAPTOR ablation is also complete. Removing RAPTOR input clipping still produced 24/24 valid, 0 strict S0-vs-S3 cases in the known failure band, so clipping is excluded as the main robustness cause there. This does not upgrade RAPTOR into a clean single-variable causal control because architecture, recurrence, input dimension, and training source remain confounded.
- Current strategic decision in V8: scope closure plus paper writing. Optional or postponed items are RQ2 statistical strengthening plus fitness ablation, a metamorphic/equivariance oracle, and a dedicated unclipped-ablation report.

## What Is Tracked

- Harness code under `scripts/`, board overlays under `boards/`, PX4 install/build helpers, configs, and patches.
- Board and patch support for `px4_sitl_mcnn_sih`, `px4_sitl_raptor_sih`, and `px4_sitl_raptor_unclipped_sih`.
- Current narrative and summary artifacts under `docs/`.
- Structured result summaries such as `results.json`, `results.jsonl`, `criteria.json`, `severity_thresholds.json`, campaign summaries, candidate lists, and theta files.
- The V8 RAPTOR full-campaign review exception: selected top-level `runs/campaigns/raptor_*_20260705/` artifacts were force-tracked for review reproducibility.

Raw run output is intentionally not tracked:

- `*.ulg`
- `*.log`
- `docs/**/evals/`
- `runs/**/evals/`
- scratch checkpoints and local campaign work directories unless explicitly force-tracked as review artifacts

Those files may exist locally as ignored evidence, but the repository state is kept to code plus compact reports and structured summaries.

## Key Docs

- `docs/PROJECT_NARRATIVE_CONTEXT_v8 (1).md`: current narrative, experiment state, contribution framing, threat model, and next decisions.
- `docs/ARTIFACT_INDEX.md`: retained artifact map.
- `docs/switch_severity_campaign_20260629.md`: switch-severity RQ1/RQ2/RQ3 campaign.
- `docs/multipolicy_differential_20260703.md`: P1-P7 differential spectrum and failure-convergence result.
- `docs/wave1_windphysics_20260627.md`: wind+physics negative.
- `docs/wave2_statecontam_campaign_20260703.md`: state-contamination negative.
- `docs/wave2_gateA_diagnostic_20260703.md`: boundary-anchor randomness and gate-methodology diagnostic.
- `docs/rq2_archive_reanalysis_20260705.md`: archive reanalysis showing guided search as fast boundary localization, not complete causal characterization.
- `docs/raptor_external_ai_review_2026-07-07.md`: RAPTOR full-campaign report and external review packet.
- `docs/raptor_unclipped_ablation_preflight_20260707.md`: unclipped RAPTOR ablation preflight and result.
- `docs/fuzz1c_decontam_20260625.md` and `docs/fuzz1c_severity_20260625.md`: strict differential rejudgment and severity lineage.
- `docs/mcnn_gonogo*.md`: `mc_nn_control` bring-up and gate results.

## Environment

Use the container path; do not rely on host PX4 binaries:

```bash
sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=<name> ./docker/run.sh bash -lc "source /opt/ros/jazzy/setup.bash && source ros2_ws/install/setup.bash && <cmd>"'
```

PX4 source and ROS workspace are ignored local dependencies:

- `external/PX4-Autopilot`
- `ros2_ws`

Tracked overlays, patches, and installers are the source of truth for regenerating those trees.

## Execution Notes

- PX4 is pinned to `3042f906abaab7ab59ae838ad5a530a9ef3df9a6`.
- Use positive controller identity gates for mode-23 work: `mcnn_identity_gate` for `mc_nn_control`, `raptor_identity_gate` for RAPTOR.
- `raptor` keeps original input clipping semantics. `raptor_unclipped` is a separate SUT backed by `patches/px4/raptor_unclipped.patch` and `px4_sitl_raptor_unclipped_sih`.
- RAPTOR runs require `policy.tar` staging and a ROS overlay matching the runtime to avoid stale message import failures.
- Campaign throughput is serial: `N=1` at `PX4_SIM_SPEED_FACTOR=1.25` is about 22-23 eval/h. Parallel campaign execution is not considered reliable because offboard setpoints are wall-clock ROS timers rather than lockstep.

## Validation Before Commit

Use the lightweight checks before committing:

```bash
python3 -m py_compile scripts/*.py
bash -n scripts/*.sh docker/*.sh
git ls-files '*.json' | xargs -r jq empty
git diff --check
git diff --cached --check
```
