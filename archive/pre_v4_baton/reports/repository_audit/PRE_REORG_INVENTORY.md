# Pre-reorganization Repository Inventory

Captured: `2026-07-12 12:17:42 -0700`
Repository: `/mnt/nvme/uav_sf`
Remote target: `git@github.com:JacksonW1025/uav_sf.git`

This inventory was recorded before any BATON reorganization or artifact move. Unknown research material is retained. Counts for ignored raw artifacts include files that do not appear in normal `git status` output.

## Git state

- Branch: `tier05-fork-20260712T090728Z` (dedicated experiment branch; no branch switch required)
- HEAD: `4dff034bde781fd3b9e1b7c7e78a01337a92d795` (`Add two-SUT campaign figures`)
- Upstream before checkpoint: none
- Remotes:
  - fetch: `origin git@github.com:JacksonW1025/uav_sf.git`
  - push: `origin git@github.com:JacksonW1025/uav_sf.git`
- Staged: none
- Modified:
  - `AGENT.md`
  - `README.md`
  - `scripts/m1_offboard_task.py`
- Deleted: none
- Untracked research roots/files observed by `git status --short`:
  - `docs/NEW_NARRATIVE_v5.md`
  - `docs/PROJECT_NARRATIVE_CONTEXT_v8 (1).md`
  - `docs/equivariance_*_20260708.md`, `docs/equivariance_stage01_analysis_20260709.md`
  - `docs/px4_*_audit_20260709.md`, `docs/px4_race_causality_*_20260709.{md,json}`
  - `docs/px4_race_r4_gate_20260709/`
  - `docs/round5_delivered_state_20260709/`
  - 12 research scripts under `scripts/`
  - 3 equivariance tests under `tests/`
  - `tier05_fork_20260712T090728Z/`
- Untracked runtime links (not research artifacts):
  - `etc -> /tmp/px4_audit_t5.P9brBk/raptor` (transient/broken audit runtime link)
  - `test_data -> /mnt/nvme/uav_sf/external/PX4-Autopilot/test_data` (external dependency link)

## Main directories before reorganization

- `boards/`: tracked PX4 SITL board overlays.
- `config/`: experiment and safety-envelope configuration.
- `docker/`: container build and launch helpers.
- `docs/`: narrative versions, reports, structured summaries, and local raw evaluation trees.
- `img/`: figure sources and rendered figures.
- `patches/`: tracked PX4 patches.
- `runs/`: selected tracked campaign review artifacts; per-evaluation raw output remains ignored.
- `scripts/`: runners, analyses, diagnostics, installers, and utilities in a flat legacy layout.
- `tests/`: repository unit tests.
- `external/`, `ros2_ws/`: ignored local dependencies/workspaces.
- `tier05_fork_20260712T090728Z/`: new Tier-0.5 legacy-versus-hardened harness campaign, approximately 8.8 GiB on disk.

## Experiment reports and research notes

Major tracked report families already present:

- F1/F2 lineage: `docs/fuzz1*_20260625.md`, `docs/switch_severity_campaign_20260629.md`.
- F2a archive reanalysis: `docs/rq2_archive_reanalysis_20260705.{md,json}`.
- RAPTOR S1/S2: `docs/raptor_external_ai_review_2026-07-07.md`, `docs/raptor_unclipped_ablation_preflight_20260707.md`, supporting tracked campaign summaries under `runs/campaigns/`.
- B1/B2/B3: `docs/wave1_windphysics_20260627.md`, `docs/wave2_statecontam_campaign_20260703.md`, `docs/multipolicy_differential_20260703.md`.
- Oracle and design notes: `docs/oracle_calibration.md`, `docs/oracle_impl_20260626.md`, `docs/oracle_map_and_property_set_v0.1.md`.
- Historical narrative versions: `docs/PROJECT_NARRATIVE_CONTEXT_v2.md`, `v5.md`, `v6.md`, and `v7.md`.

New untracked reports/notes retained for the checkpoint:

- `docs/NEW_NARRATIVE_v5.md` (user-designated current BATON narrative source).
- `docs/PROJECT_NARRATIVE_CONTEXT_v8 (1).md` (immediately preceding narrative context).
- Equivariance probe preflight/results/stage-01 analysis.
- PX4 actuator attribution, delivered-state, guard-slot, provenance/handoff, race-causality, and Round-5 reports.
- `tier05_fork_20260712T090728Z/REPORT.md` and its frozen rules, provenance, run index, analysis, and verdict.

## Logs and data

- Existing Git policy ignores `*.ulg`, `*.log`, `docs/**/evals/`, and `runs/**/evals/`.
- Tier-0.5 campaign:
  - 144 attempts, 144 valid runs according to its report/index.
  - 144 ULogs, task JSON records, metrics, `r4_record.json`, and per-run console/agent/topic logs.
  - 1,008 `.ulg`/`.log` files totaling `9,187,397,572` bytes.
  - Full directory size: approximately 8.8 GiB (`du` allocation; byte totals and allocation differ).
- PX4 Round-4 race gate:
  - 42 `.ulg`/`.log` files totaling `382,993,321` bytes.
  - Full directory size: approximately 372 MiB.
- Round-5 delivered-state directory: 15 structured files, approximately 3.5 MiB, no raw `.ulg`/`.log` files.
- Existing tracked structured data include campaign summaries, candidate/theta files, JSON/JSONL outputs, figures, and selected review artifacts.
- Raw files have not been edited or overwritten during this inventory.

## Analysis, runner, monitor, and diagnostic scripts

The repository contains a flat `scripts/` layout. Recognizable groups include:

- Runners: `m1_diff_runner.py`, `campaign_runner.py`, `route_a_anchor_regression.py`, `run_switch_dense_sweep.py`, `run_raptor_unclipped_ablation.py`, `run_equivariance_probe.py`, `tier05_fork_campaign.py`.
- Analysis: `m1_metrics.py`, `rq2_archive_reanalysis.py`, `equivariance_floor_analysis.py`, `px4_race_causality_round4.py`, `px4_delivered_state_round5.py`, figure-generation scripts under `img/`.
- Contract/oracle monitoring: `property_oracle.py`, `property_fitness.py`, `validity_automation.py`.
- Diagnostics: `px4_actuator_attribution_audit.py`, `px4_mixer_fingerprint_round5.py`, `px4_race_r4_experiment.py`, `px4_rq3_redraw_round5.py`, `m2b_*` scripts.
- Utilities/installers: provenance archiver, clone/build/install shell scripts, and `theta_genome.py`.

## PX4 overlays, patches, and ignored external worktree

- PX4 pin: `3042f906abaab7ab59ae838ad5a530a9ef3df9a6`.
- Tracked board overlays: `boards/px4/sitl/{mcnn_sih,raptor_sih,raptor_unclipped_sih}.px4board`.
- Tracked patches: `patches/px4/m2b_state_shim.patch`, `patches/px4/raptor_unclipped.patch`.
- Tracked installers reproduce the custom SIH airframe, DDS ground-truth topics, state shim, and boards.
- The ignored PX4 worktree is dirty. Research-relevant modifications are EKF2/M2B shim code, unclipped RAPTOR, ground-truth/DDS support, board files, and the SIH airframe. Verification before checkpoint showed:
  - both tracked patches pass `git apply --reverse --check` against the local PX4 tree;
  - all three tracked board overlays compare byte-for-byte equal to their local PX4 copies;
  - the custom airframe/CMake registration is generated by tracked `scripts/install_m1_sih_x500.sh`;
  - nested submodule pointer changes are dependency/worktree noise and are not treated as experiment results.
- `ros2_ws/src/px4_msgs` had no reported tracked or untracked modification.

## Unknown or uncertain material

- The equivariance campaign is identifiable as a research probe, but its final BATON scenario/claim role is not yet verified; retain and index as `uncategorized`/`needs_review` unless a report establishes a narrower classification.
- PX4 Round-5 redraw/delivered-state artifacts are mechanism diagnostics; exact claim ownership remains `needs_review` where reports do not close writer attribution.
- The Tier-0.5 campaign is a harness differential. Its structured result is confirmed for its preregistered anchors; raw evaluation trees remain local pending safe external archival because Git LFS is unavailable.
- The root `etc` and `test_data` links are runtime/dependency links rather than owned research artifacts and are explicitly ignored.

## Large files and LFS

- `git lfs` is not installed and no LFS tracking rules or LFS objects are present.
- The large material is dominated by 144 Tier-0.5 ULogs/runtime roots (approximately 8.8 GiB) and Round-4 raw gate output (approximately 372 MiB).
- Individual ULogs are approximately 30–32 MiB in the inspected samples; runtime-root copies account for additional volume.
- These raw artifacts exceed a practical normal Git/GitHub checkpoint. They will not be deleted or silently omitted: structured summaries and per-run JSON are checkpointed; raw files will be safely moved outside the repository and recorded by original path, external path, size, and SHA-256 in the final artifact manifest/report.

## Sensitive-information review

- Suspicious filename scan found no `.env`, credential, token, private-key, or password file in the candidate main-repository research material.
- Content scan for common API key, access token, bearer token, password, private key, GitHub token, and AWS key patterns found no candidate file.
- Test certificates/keys under ignored third-party dependency/build trees are upstream fixtures and are not candidates for this repository commit.
- No secret value was printed during the audit.

## Recognized experiment IDs and aliases

- F1 anchor -> S1 commanded switch-in / mc_nn.
- F2 campaign -> S1 commanded switch-in / mc_nn.
- F2a archive reanalysis -> S1 commanded switch-in / mc_nn, legacy-harness evidence boundary applies.
- S1 RAPTOR campaign -> S1 commanded switch-in / RAPTOR.
- S2 RAPTOR unclip -> S1 commanded switch-in / RAPTOR mechanism/control contrast.
- B1 -> wind + physics supporting control.
- B2 -> state contamination supporting control.
- B3 -> multi-policy supporting control.
- D1 -> setpoint amplitude supporting control (identified alias; exact artifact mapping needs review).
- D2 -> fault injection supporting control (identified alias; exact artifact mapping needs review).
- Tier-0.5 / THE FORK -> harness differential: legacy wall-clock versus hardened sim-time/lockstep event clock.
- PX4 Round 4 -> allocation freshness and single-writer mechanism observation; counterfactual gate failed.
- PX4 Round 5 -> delivered-state/writer-attribution diagnostic, `needs_review` where causal closure is absent.
- Equivariance probe -> `uncategorized`, `needs_review`.

## Evidence-boundary guardrails for reorganization

- `confirmed`: supported by code/log/trace/commit/repeated experiment.
- `mechanism_observed`: implementation difference confirmed; physical consequence not yet confirmed.
- `planned`: experiment design exists but is not complete.
- `legacy_unverified`: old wall-clock harness result requiring hardened-harness confirmation.
- No result number, raw artifact, historical commit/tag, or legacy alias is to be rewritten during reorganization.
