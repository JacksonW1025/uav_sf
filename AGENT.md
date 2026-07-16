# Agent guide

## Required first-read order

1. `docs/narrative/CURRENT_NARRATIVE.md`
2. `config/dependencies.lock.yaml`
3. `docs/motivation/README.md`
4. `docs/design/ROUTE_MODEL.md`
5. `docs/design/OBSERVABILITY_MATRIX.tsv`
6. `docs/repository/REPOSITORY_MAP.md`
7. `AGENT.md`

The current narrative and dependency lock are authoritative.

## Current boundary

Family A is primary. Work in this phase is limited to dependency locking,
Family A bootstrap, P-1 observability, M2 registration evidence, M4 official
test coverage, and a gated normal-flow P0 baseline. Do not start a complete
fuzzer, random search, fault campaign, or later-phase probe.

Treat a route as the declared mode plus registration, authority source,
producer identity, setpoint interface and freshness, controller/module path,
allocator input, actuator writer/output, failsafe state, and fallback target.
A mode label or waypoint update alone is not a route transition.

## Evidence rules

- Separate requested mode, registration, activation, data consumption,
  fallback selection, and complete fallback installation.
- Preserve exact repository commit, source path, symbol, assertion, timestamp
  domain, and collection method.
- Use only the enumerations defined by the TSV/schema contracts.
- Mark unknowns honestly. Never turn a template, example, or old result into an
  observation.
- Family B material is optional and isolated in `family_b/`; it is not used by
  the default bootstrap or Motivation Study.
- Historical conclusions require a new route-aware reproduction before reuse.

## Repository rules

- Keep generated dependencies in ignored `external/` and `ros2_ws/` trees.
- Keep raw runtime artifacts in ignored `runs/`; track compact summaries only.
- Represent PX4 source changes as commit-pinned, idempotent patches.
- Keep Common Behavior Core independent of ROS 2, PX4 messages, and Family B.
- Keep Family A code free of learned-controller and old campaign types.
- Preserve unrelated user changes and inspect `git status` before edits.

Run `./scripts/validation/validate_repo.sh` before each handoff. A completed
change has passing tests, no unexpected untracked or ignored tracked files, no
tracked raw runs, no file larger than 10 MiB, and a clean synchronized branch.
