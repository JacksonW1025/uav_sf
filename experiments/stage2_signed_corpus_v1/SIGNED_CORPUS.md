# Stage 2 core corpus — signed

## What is signed

The seven core actions of the conditional freeze, each implemented, selectable
by policy, qualified in flight, and consistent with the evidence.

| Action | Phase | Application | Instances | Precondition held |
| --- | --- | --- | ---: | ---: |
| `stop_owned_setpoint_stream` | execution | runtime | 80 | 80 |
| `terminate_owning_producer` | fallback | runtime | 18 | 18 |
| `adjacent_land_request` | replacement | runtime | 30 | 30 |
| `re_enter_route_after_successor` | re-entry | runtime | 23 | 23 |
| `restart_producer_after_loss` | fallback | runtime | 1 | 1 |
| `exhaust_registration_capacity` | registration | runtime | 8 | 8 |
| `withhold_health_reply` | activation | launch | 11 | 11 |

Replay: [precondition-check.json](precondition-check.json), per instance in
[per-instance.jsonl](per-instance.jsonl), declarations in
[core-actions.json](core-actions.json). 230 attempts — the 213 accepted attempts
of the five closed formal studies plus the 18 of the qualification flown under
the corrected loss recording. No predicate is inconsistent and none is
unvalidated.

Qualification: [the Step E batch](../step_e_signed_corpus_qualification_v1/qualification.result.json)
selected and applied the corpus across two mechanisms and three strategies, with
17 of 18 attempts passing and one lost to the known clock flake. The earlier
[full-corpus batch](../step_d_full_corpus_qualification_v1/QUALIFICATION.md)
passed 18 of 18 on the same corpus before the loss-recording fix.

## Frozen with it

- Two compared mechanisms: `legacy_offboard` and `dynamic_external_mode`.
  Registration and health actions are dynamic-only because legacy offboard has
  neither protocol.
- The `straight_line` moving workload with trajectory setpoints, except for the
  refused-activation episode, which declares a workload without motion.
- Five ordered timing bins per timed action, each spanning that action's own
  feasible window, anchored on that action's own marker.

## How the last inconsistencies were resolved

Three corrections, none of which relaxed a contract:

1. **A precondition is read where it was evaluated.** A timed action is judged
   at the executor's decision moment; a launch configuration, which has no such
   moment, at its effect. Judging everything at the decision moment was tried
   first and made the picture worse.
2. **A producer loss is recorded where telemetry shows it.** It had been learned
   by polling the producer process, about eleven seconds behind the vehicle's
   own navigation state, so the evidence disagreed with what the executor and
   the failsafe already knew.
3. **A reclaim's own loss is its setup, not a separate action.** The reclaim is
   legal only after a loss, so the loss inside a reclaim episode has no decision
   of its own; counting it as an independent firing measured the fixture rather
   than the generator.

## Boundary

Signing records that the corpus is implemented, reachable and self-consistent.
It establishes nothing about PX4 behaviour, no defect, and no comparison between
strategies. Every flight behind it is non-formal and contributes to no
denominator.

Stage 2 is closed. The next stage builds the closed-loop generation this corpus
exists to feed.
