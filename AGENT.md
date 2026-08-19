# Repository agent rules

## Authority and synchronization

- `codex-b` and `cc-b` are the key development branches. Both carry
  authoritative work; neither may silently discard or overwrite the other.
- `main` and `origin/main` are synchronized publication mirrors of reviewed
  development state; they are not independent sources of truth.
- A development branch takes the other branch's reviewed work by
  fast-forwarding from `main`, and publishes its own by moving `main` to the
  reviewed development commit. Start new work from an up-to-date branch.
- Never merge an older `main` into a development branch merely to make
  histories agree. Inspect divergence, preserve a recovery reference when
  rewriting a published tip, then move `main` to the reviewed commit.
- Fetch remote references before publishing so divergence is explicit, but
  base research and implementation decisions on the development branches and
  the current normative documents.
- When the two development branches diverge, resolve it explicitly against the
  normative documents and the closed evidence. Do not resolve it by dropping a
  published milestone from either side.
- Confirm a clean worktree before experiments, branch synchronization, or
  release operations. Ordinary code changes may begin from a deliberately
  dirty worktree only after the existing modifications are understood and
  preserved.

## Narrative authority

- `docs/NEW_NARRATIVE_v8.md` is the sole paper-narrative source.
- `docs/CURRENT_STATUS.md` records completed implementation and evidence;
  proposed work must not be reported there as complete.
- `docs/RESEARCH_SCOPE.md`, `docs/ROUTE_MODEL.md`, `docs/METHOD.md`, and
  `docs/EXPERIMENT_PLAN.md` define the implementation-facing scope, target
  state, method obligations, and decision gates.
- A frozen experiment report, preregistration, ledger, or attestation remains
  authoritative for its own identity and denominator. Narrative updates never
  rewrite closed evidence.
- `docs/STAGE_EXECUTION_LOG.md` records step-by-step execution state so work can
  be resumed without prior context. Update it in the same commit as the work it
  describes, and never record proposed work there as complete.

## Research boundary

- Only Family A route-replacing authority transitions are in scope.
- Supported mechanisms are PX4 internal routes, Legacy Offboard, Dynamic
  External Mode, Mode Executor, and internal Hold, RTL, Land, or Recovery.
- Do not introduce controller replacement, actuator-level authority transfer,
  unrelated workload frameworks, or any other research family.
- A mode label alone is never accepted as route-transition evidence.
- The target paper method requires full semantic route/contract state and
  closed-loop action-sequence plus timing generation. The existing bounded
  timing selector is a prototype and must not be presented as the completed
  method.
- The upper mission and behavior stack supplies realistic seeds, reachability,
  and full-stack replay; it is not the defect target.

## Evidence and implementation

- Preserve route epoch, producer/session, registration, activation, command
  subject time, controller, allocator, writer, lifecycle owner, executor owner,
  expected successor, and expected fallback identity.
- Run the Evidence Admissibility Gate before interpreting Oracle output.
- Missing or incomplete evidence must remain `INCONCLUSIVE` or `UNKNOWN`.
- Keep research-contract exposure, reproducible contract violation,
  source-grounded PX4 defect, and safety-relevant finding as separate result
  levels.
- Keep dependencies, source commits, images, and packages pinned to immutable
  identities.
- Keep runtime output in ignored `runs/`; never track flight artifacts.
- Do not treat the current checkout host or the repository's validation image
  as the formal experiment environment. Register the actual target environment
  in each new plan and require its matching trace attestation.
- Run `./scripts/validation/validate_repo.sh` before handoff.
