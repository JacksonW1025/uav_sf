# Testing Route-Replacing Authority Transitions in PX4

This repository studies what happens when PX4 declares that the primary control path has moved from Route A to Route B. A route-replacing authority transition is more than a mode-label change: the old producer/path must be revoked, the new path must be completely installed, the transition window must remain exclusive and continuous, and a failure must restore the complete intended safe route.

The four core questions are:

1. Was the old route revoked in time?
2. Was the new route fully installed?
3. Was the transition window exclusive and gap-free?
4. Was the safe fallback route fully restored after failure?

## Subject families

- **Family A (primary):** PX4 Internal Route ↔ ROS 2 Offboard ↔ Dynamic External Mode ↔ Internal Fallback / RTL / Land / RC takeover.
- **Family B (deep representative case):** PX4 Classical Cascade ↔ Registered Learned Controller ↔ Classical Fallback.

The existing mc_nn, RAPTOR, and classical-controller evidence is preserved as legacy Family B material. It does not count as direct evidence for Family A until it is revalidated with the route-oriented harness.

## Current phase

The repository is in the **Motivation Study** phase. The immediate gate is **P-1 Route Observability Feasibility**, followed by M1–M5 evidence collection and focused probes. Large-scale fuzzing and full fuzzer development are out of scope for this phase.

Start here:

1. [Current narrative](docs/narrative/CURRENT_NARRATIVE.md)
2. [Motivation Study workspace](docs/motivation/README.md)
3. [Route model](docs/design/ROUTE_MODEL.md)
4. [Observability matrix](docs/design/OBSERVABILITY_MATRIX.tsv)
5. [Repository map](docs/repository/REPOSITORY_MAP.md)

## Environment bootstrap

Docker is the supported baseline. The clone/setup scripts accept environment-variable overrides and keep build/runtime logs under ignored `runs/` paths.

```bash
./docker/build.sh
./scripts/setup/clone_px4.sh
./scripts/setup/setup_ros2_ws.sh
./docker/run.sh bash
```

The PX4 and ROS 2 source/build trees under `external/` and `ros2_ws/` are local dependencies, not canonical research artifacts. PX4 changes must be reproduced from tracked [boards](boards/), [patches](patches/), and installer scripts.

## Repository navigation

- `docs/narrative/`: sole current narrative and scope.
- `docs/motivation/`: M1–M5 inventories and evidence templates.
- `docs/design/`: route semantics, observability fields, and route-profile schema.
- `experiments/`: Motivation Study, probe, and testcase templates only.
- `scripts/`: active setup, tracing, probes, analysis, and validation tools.
- `boards/`, `patches/`, `config/`: reproducible PX4 overlays and the minimal Family B profile.
- `data/`: compact manifests, processed summaries, and trace policy.
- `archive/pre_v4_baton/`: prior BATON narratives, experiments, reports, scripts, configs, figures, and indexes.

## Data policy

Do not commit ULogs, runtime logs, checkpoints, per-evaluation trees, build/install output, or large raw traces. Store them outside the repository and add a compact aggregate entry to [the external archive manifest](data/manifests/PRE_V4_EXTERNAL_ARCHIVE.tsv). `runs/` is runtime-only and remains ignored.

## Validation

Use one command before committing:

```bash
./scripts/validation/validate_repo.sh
```
