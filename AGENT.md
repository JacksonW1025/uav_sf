# Agent guide

## First-read order

1. `docs/narrative/CURRENT_NARRATIVE.md`
2. `docs/motivation/README.md`
3. `docs/design/ROUTE_MODEL.md`
4. `docs/design/OBSERVABILITY_MATRIX.tsv`
5. `docs/repository/REPOSITORY_MAP.md`
6. `AGENT.md`

## Current tasks

Work is currently limited to:

- **P-1 Route Observability Feasibility**
- **M2 External Mode and Registration Importance**
- **M4 Official Test Coverage Gap**
- **P0 Official Handoff Flow**

Family A is the primary subject. Family B is retained as a deep-route representative case and future cross-family validation source.

## Route semantics

A route is a runtime tuple, not a mode label. At minimum, reason about declared mode, registration state, authority source, producer identity, setpoint level/topic/freshness, enabled and bypassed modules, allocator input, actuator writer/output, failsafe state, and fallback target.

A trajectory update within the same authority/producer/module path is not a handoff. A declared mode is not sufficient evidence that the intended data-plane route was installed.

## Repository rules

- Keep all work on `main` unless the user explicitly changes the policy.
- Do not start large-scale fuzzing immediately after cleanup.
- Do not treat old BATON conclusions as Family A evidence.
- Do not count an ordinary trajectory update as a route handoff.
- Do not treat mode state as the complete runtime route.
- Do not commit raw logs, ULogs, runtime trees, checkpoints, or build/install output.
- Do not retain unreproducible changes inside ignored PX4 source trees. Capture changes as tracked patches, overlays, or installers.
- Use `runs/` only for ignored runtime output and `data/processed/` only for compact, reviewable derived summaries.
- Record unknowns as `TBD`, `NEEDS_REVIEW`, or `not_collected`; never invent Motivation Study observations.

## Canonical commands

```bash
./scripts/setup/clone_px4.sh
./scripts/setup/setup_ros2_ws.sh
./scripts/validation/validate_repo.sh
```

Legacy commands and old experiment paths are provenance under `archive/pre_v4_baton/`; they are not current entry points.
