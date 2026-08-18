# Repository agent rules

## Authority

- `codex-b` is the authoritative development branch. `main` and
  `origin/main` are reviewed publication mirrors.
- `docs/NEW_NARRATIVE_v8.md` is the sole research narrative.
- The Chinese and English experiment plans must keep the same numbered gates,
  status, deliverables, exit criteria, and stop rules.
- A retained experiment package is authoritative only for its own identity,
  evidence, and denominator.

## Current execution state

- Repository consolidation (Stage 0) is complete.
- No V8 plan schema, observation patch, flight image, evaluator, runner, or
  formal matrix is active.
- Do not run or add a flight/formal entry point before its preceding plan gate
  is complete and the boundary validator is updated intentionally.
- A passing repository validation is not flight readiness or method evidence.

## Scope

- Work only on Family A route-replacing authority transitions across PX4
  internal routes, Legacy Offboard, Dynamic External Mode, Mode Executor, and
  internal Hold/RTL/Land/Recovery.
- The target method requires independently supported Runtime Route Instance
  evidence, full semantic state, and closed-loop action-sequence plus timing
  generation.
- Official/handwritten scenarios are a separate practice reference. The core
  comparison contains grammar-aware random, systematic enumeration,
  feedback-free state-conditioned generation, and full state/feedback-guided
  generation.
- The upper mission/behavior stack supplies seeds, reachability, and full-stack
  replay; it is not the defect target.

## Evidence discipline

- Distinguish observed, derived, inferred, and constant identity fields.
- Do not treat allocator publication and actuator write/effect as independent
  evidence unless they come from independent observation boundaries.
- Overall admissibility must eventually combine trace, environment, clock,
  identity, and physical validity. The retained primitive Gate is incomplete.
- Keep research exposure, reproducible contract violation, source-grounded PX4
  defect, and safety-relevant full-stack finding separate.
- Missing evidence remains `INCONCLUSIVE` or `UNKNOWN`.
- Formal campaign statistics use campaigns, not launches or episodes, as the
  independent unit.

## Tracked-tree policy

- `experiments/` is an explicit allowlist enforced by
  `scripts/validation/validate_repo.py`.
- Old active patch bundles, plan templates, timing-strategy runners, and
  process-exit preregistration must not be restored into the current tree.
- Git history is the recovery path for deleted material.
- Keep runtime artifacts under ignored `runs/`; do not modify ignored state as
  part of a tracked-tree cleanup.
- Run `./scripts/validation/validate_repo.sh` before handoff.
