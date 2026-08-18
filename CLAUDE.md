# Repository guidance

This checkout is a V8 research testbed at the boundary between completed
Motivation evidence and method construction. Read [AGENT.md](AGENT.md) first.

## Sources of truth

- Research narrative: [docs/NEW_NARRATIVE_v8.md](docs/NEW_NARRATIVE_v8.md)
- Current facts: [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md)
- Retention/scope audit: [docs/V8_REPOSITORY_AUDIT.md](docs/V8_REPOSITORY_AUDIT.md)
- Detailed runbook: [docs/EXPERIMENT_PLAN.zh-CN.md](docs/EXPERIMENT_PLAN.zh-CN.md)
- English mirror: [docs/EXPERIMENT_PLAN.md](docs/EXPERIMENT_PLAN.md)

## Current architecture

The active code is intentionally limited to partial primitives:

1. `scripts/model/` and `data/schemas/route_event.schema.json` define the
   current route-event skeleton and ten-field Runtime Route Instance target.
2. `scripts/adapters/` and `scripts/collectors/` retain source normalization,
   hash-chained raw collection, clock fitting, and ULog extraction. There is no
   active normalized-trace closure.
3. `scripts/oracles/` retains contract primitives. The current evidence Gate
   is not the final combined V8 Gate and cannot authorize execution.
4. `scripts/accounting/`, `scripts/safety/`, and selected `scripts/runtime/`
   modules retain append-only accounting, safety/cleanup, artifact hashing,
   isolation, physical-takeoff, and Stage A2 workload primitives.
5. `runtime/ros2/` retains in-scope workload components, but no active patch,
   flight image, runner, plan, or evaluator wires them together.

Earlier high-level plan/evaluator/campaign/strategy/analysis entry points were
removed. Do not recreate them by copying old code; implement new components at
the corresponding V8 plan gates.

## Commands

```bash
# Full Stage 0 boundary validation
./scripts/validation/validate_repo.sh

# Static boundary validation only
python3 -m scripts.validation.validate_repo

# Remaining primitive unit tests
python3 -m unittest discover -s tests -v

# Optional ARM64 validation image
docker buildx build --platform linux/arm64 \
  --file containers/family_a/Dockerfile \
  --tag uav-sf-v8-validation:local .
```

There is deliberately no supported flight or formal experiment command.

## Validation contract

The validator enforces the retained experiment allowlist, absence of removed
active paths, the two active partial schemas, source/container lock identities,
Markdown links, importability, unit tests, shell syntax, and Git whitespace.
Update its allowlists only when the corresponding experiment-plan gate has
produced reviewed evidence for the new tracked content.

A passing validation means V8 scope consistency only. It does not establish
independent identity observation, combined admissibility, a confirmed finding,
semantic-state extraction, generator correctness, concurrency qualification,
or method effectiveness.
