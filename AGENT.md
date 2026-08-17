# Repository agent rules

## Authority and synchronization

- `origin/main` is the authoritative repository state.
- Fetch `origin` with pruning before any code investigation.
- Confirm that the worktree is clean before changing files.
- Base work on the fetched `origin/main`, not on an unverified local branch.

## Research boundary

- Only Family A route-replacing authority transitions are in scope.
- Supported mechanisms are PX4 internal routes, Legacy Offboard, Dynamic
  External Mode, Mode Executor, and internal Hold, RTL, Land, or Recovery.
- Do not introduce controller replacement, actuator-level authority transfer,
  unrelated workload frameworks, or any other research family.
- A mode label alone is never accepted as route-transition evidence.

## Evidence and implementation

- Preserve route epoch, producer/session, registration, activation, command
  subject time, controller, allocator, writer, lifecycle owner, executor owner,
  expected successor, and expected fallback identity.
- Run the Evidence Admissibility Gate before interpreting Oracle output.
- Missing or incomplete evidence must remain `INCONCLUSIVE` or `UNKNOWN`.
- Keep dependencies, source commits, images, and packages pinned to immutable
  identities.
- Keep runtime output in ignored `runs/`; never track flight artifacts.
- Do not treat the current checkout host or the repository's validation image
  as the formal experiment environment. Register the actual target environment
  in each new plan and require its matching trace attestation.
- Run `./scripts/validation/validate_repo.sh` before handoff.
