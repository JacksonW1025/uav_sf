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

Family B (classical cascade ↔ registered controller ↔ classical fallback) has
revision-locked static mechanism evidence but no accepted runtime evidence. It
remains a future independent cross-depth study.

## Current phase

M-FINAL closed the bounded Motivation Study as `CONDITIONALLY_COMPLETE` with
disposition
`CONDITIONAL_PASS_MOTIVATION_COMPLETE_AUTHORIZE_FAMILY_A_FUZZER_V0`.
The core Motivation and Family A formal empirical scope are supported. R1
session rollover, W1 real-workload runtime value, Family B runtime generality,
state-aware search gain, and full fuzzing effectiveness are not established.

The exact next action is to create and push an independent Family A Fuzzer v0
preregistration. No fuzzer implementation, runtime, random campaign, large
campaign, real-workload campaign, or Family B campaign has started.

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
4. [Motivation final report](docs/motivation/MOTIVATION_STUDY_FINAL_REPORT.md)
5. [Route model](docs/design/ROUTE_MODEL.md)
6. [Observability matrix](docs/design/OBSERVABILITY_MATRIX.tsv)
7. [Repository map](docs/repository/REPOSITORY_MAP.md)
8. [Agent guide](AGENT.md)

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
