# uav_sf

This repository contains the PX4 SITL harness and experiment artifacts for multi-oracle scenario fuzzing of learned UAV flight controllers.

The authoritative project state is `docs/PROJECT_NARRATIVE_CONTEXT_v2.md`. That document supersedes the old RAPTOR/M0/M1/M2 handoff material and locks the current narrative before Route B starts.

## Current State

- Route A is closed: the mc_nn activation line produced 4 strict `primary_bug` cases after severity classification and symmetric infrastructure decontamination.
- The headline bug is classical control-level S0 recovery versus `mc_nn_control` S3 loss of control/tumble under matched violent handoff states.
- The important method result is that a reliable differential oracle needs state-aligned switching, graded severity, and infrastructure decontamination.
- Route B has not started: next work is multi-oracle scenario fuzzing, beginning with metamorphic/symmetry and controlled dense scans around the FUZZ-1c non-monotonic failure band.

## What Is Tracked

- Harness code under `scripts/`, board overlays under `boards/`, PX4 install/build helpers, configs, and patches.
- Current narrative and summary artifacts under `docs/`.
- Structured result summaries such as `results.json`, `results.jsonl`, `criteria.json`, and `severity_thresholds.json`.

Raw run output is intentionally not tracked:

- `*.ulg`
- `*.log`
- `docs/**/evals/`

Those files may exist locally as ignored evidence, but the repository state is kept to code plus compact reports/structured summaries.

## Key Docs

- `docs/PROJECT_NARRATIVE_CONTEXT_v2.md`: current narrative, experiment state, and next-route instructions.
- `docs/ARTIFACT_INDEX.md`: retained artifact map.
- `docs/fuzz1c_decontam_20260625.md`: strict differential rejudgment.
- `docs/fuzz1c_severity_20260625.md`: severity scan that fed the decontamination pass.
- `docs/fuzz1b_locked_20260625.md` and `docs/fuzz1_activation_20260625.md`: earlier FUZZ lineage, now explicitly superseded by the FUZZ-1c/decontam result.
- `docs/RAPTOR_closeout.md`: RAPTOR robustness closeout.
- `docs/mcnn_gonogo*.md`: mc_nn_control bring-up and gate results.

## Environment

Use the container path; do not rely on host PX4 binaries:

```bash
sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=<name> ./docker/run.sh bash -lc "source /opt/ros/jazzy/setup.bash && source ros2_ws/install/setup.bash && <cmd>"'
```

PX4 source and ROS workspace are ignored local dependencies:

- `external/PX4-Autopilot`
- `ros2_ws`

Tracked overlays/installers are the source of truth for regenerating those trees.

## Validation Before Commit

Use the lightweight checks before committing:

```bash
python3 -m py_compile scripts/*.py
bash -n scripts/*.sh docker/*.sh
git ls-files '*.json' | xargs -r jq empty
git diff --check
git diff --cached --check
```
