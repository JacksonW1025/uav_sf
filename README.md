# Testing Route-Replacing Authority Transitions in PX4

This repository tests whether PX4's declared transition from Route A to Route B
matches the complete runtime control route. A transition is correct only when
the old route is revoked, the target route is fully installed, the transition
is exclusive and continuous, and a failure restores the complete safe route.

Family A is the primary subject:

```text
PX4 Internal Route
↔ ROS 2 Offboard
↔ Dynamic External Mode
↔ Internal Fallback / RTL / Land / RC takeover
```

Family B (classical cascade ↔ registered learned controller ↔ classical
fallback) is retained only as a future cross-family case under `family_b/`.

## Current phase

Phase A locks dependencies and establishes route observability before any
large experiment. The ordered deliverables are:

1. Family A dependency lock and reproducible bootstrap;
2. P-1 route-observability feasibility;
3. M2 External Mode registration evidence;
4. M4 official-test coverage audit;
5. P0 normal handoff baselines, only if the P-1 gate passes.

This phase does not develop a complete fuzzer or start random campaigns.

## Quick start

The canonical environment is Ubuntu 24.04, ROS 2 Jazzy, and Gazebo Harmonic.
All source repositories are checked out at the exact revisions in
`config/dependencies.lock.yaml`.

```bash
./scripts/setup/bootstrap_family_a.sh
```

Dependency sources and builds live in ignored `external/`, `ros2_ws/`, and
`runs/` trees. Only compact processed summaries belong in Git.

## Start here

1. [Current narrative](docs/narrative/CURRENT_NARRATIVE.md)
2. [Dependency lock](config/dependencies.lock.yaml)
3. [Motivation study](docs/motivation/README.md)
4. [Route model](docs/design/ROUTE_MODEL.md)
5. [Observability matrix](docs/design/OBSERVABILITY_MATRIX.tsv)
6. [Repository map](docs/repository/REPOSITORY_MAP.md)
7. [Agent guide](AGENT.md)

## Data and validation

Raw ULogs, build output, logs, and runtime traces stay in ignored `runs/` or
external storage. Commit only compact, source-identified summaries under
`data/processed/`.

```bash
./scripts/validation/validate_repo.sh
```

Historical material is recoverable from the protected Git tag described in
[legacy recovery](docs/repository/LEGACY_RECOVERY.md); it is not current
Family A evidence.
