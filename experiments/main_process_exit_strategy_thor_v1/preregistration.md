# Moving process-exit strategy study — frozen pre-registration

Status: **FROZEN / FORMAL CAMPAIGN NOT STARTED**  
Paper role: **Section 7 method evaluation, second executable action grammar and formal-run-readiness milestone**

This study tests one action that is distinct from the already completed healthy
setpoint-stall slice. While the selected external route is active and the
vehicle has entered straight-line motion, the shared live backend requests
termination of the active external control producer. The outcome of interest is
not whether PX4 contains a bug; it is whether each strategy produces admissible
tests of control-source loss and whether PX4 installs the preregistered safe
public fallback.

## Frozen action and Oracle contract

- Backend: `owned_process_exit_fallback_v1`.
- Action: `process_exit`.
- Required observed state: `route_active=true` and `motion_entered=true`.
- Timing interval relative to observed route activation: 3.5–6.5 s.
- Official offset: 5.0 s.
- One durable `strategy-action.request.json` and exactly one
  `action_requested` record are required per attempt.
- Legacy Offboard records producer exit and shuts down; its required safe
  fallback is `internal_land`.
- Dynamic External Mode exits with reserved stimulus status 74; its required
  safe fallback is `internal_rtl`, followed by cleanup landing.
- An accepted qualification or formal attempt must be `ADMISSIBLE`, have
  `physical_execution=PASS`, and have
  `successor_progression.safe_fallback=PASS`. Oracle `VIOLATION` remains an
  accepted observation and is not a driver failure.

## Frozen comparison

The matrix crosses two mechanisms with three strategies:

1. `official_sequence`;
2. `bounded_random_timing`;
3. `state_aware`.

Every cell has a fixed budget of three launches and a required accepted count
of three, for 18 launches total. There are no adaptive top-ups. Simulation
seeds are paired across mechanisms by ordinal. Random and state-aware strategy
seeds are fixed in `matrix.json`. State-aware coverage is derived only from a
previous successful live `action_requested` record in the same
mechanism-strategy cell.

The primary comparison outputs are admissible evidence yield, executed timing
boundary coverage, applicable contract-boundary coverage, violation-signature
coverage, launches to first violation, and request timing error. This small
fixed-budget study is a second vertical slice, not a complete route/action
corpus evaluation and not evidence of strategy superiority by itself.

## Qualification history and frozen safety scope

The first complete non-formal qualification produced 16 accepted attempts and
two safety-stop attempts. Both stopped during a correct Dynamic RTL-to-Land
terminal descent: RTL climbed to at most 5.395416 m, so a generic 5.0 m
cumulative altitude-loss limit censored the expected landing. The action,
fallback, and other physical guards were not relaxed.

The frozen process-exit safety configuration changes only that cumulative
altitude-loss limit to 6.0 m. Horizontal speed, vertical speed, attitude,
body-rate, unexpected-ground-contact, collector, heartbeat, and runtime limits
remain unchanged. A subsequent concurrency race in qualification environment
initialization was refused before processing and is retained separately; the
final runner serializes the environment attestation before opening the live
barrier.

The final qualification uses a new image, new study ID, and new seeds. Its six
units all passed 3/3: 18/18 attempts are `ACCEPTED`, `ADMISSIBLE`, physically
valid, action-contract complete, and safe-fallback passing. State-aware selected
boundary → pre-boundary → post-boundary on both mechanisms, with each later
decision containing exactly the coverage observed before it.

## Frozen identities

- Candidate revision: `eebaefe79a3ee5ac3f952aa76bf9bdbcaa7d201c`.
- Image: `uav-sf-family-a-thor:process-exit-final-eebaefe`.
- Image ID: `sha256:1b8e2285aa85e81393d866b7165557996b3001597ce3506fee211497dfbd1867`.
- Environment: `thor-process-exit-strategy-final-20260818-v1`.
- Matrix digest: `sha256:032342321b1c4ab3928679004489de3cb308d65bd25e1e519bd41df069203249`.
- Final qualification result digest:
  `sha256:b4e2fb06138120b1248baae5ae68293e3f446156ce6743cd68f10e5b5543d6ab`.
- Method digest:
  `sha256:0696b69ec9766e5430f75892caa4bae755d42fb08eda56be3549bd248ecbda4c`.
- Safety digest:
  `sha256:b42e681e8bd814216b144e427e14ffc6286d6d92a29a3ba952b93316edea4bf1`.
- Action/strategy digest:
  `sha256:7f3d06954b0f6bdc07cbed076d7408cfdfd39f6ba870955518fd298915a931fc`.

`readiness-verification.json` records a six-cell dry-run with zero launches,
exact identity checks, and negative tests proving that an action/backend
mismatch is refused. At freeze time `attempt-ledger.jsonl` does not exist.

## Stop rule for this milestone

Stop after matrix validation, dry-run, negative fail-closed checks, and this
pre-registration freeze. Do not invoke `formal_attempt` or
`run_fixed_budget_campaign`; do not create a formal ledger or count any formal
denominator. Starting the 18-launch campaign is a separate, explicit next
decision.
