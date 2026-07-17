# Transition Grammar v0

## Grammar

The grammar is a typed event schedule, not executable text. Array order is
semantic. Times are relative to the start of the measured transition window.

```ebnf
case              = admission? active_phase event+ recovery? ;
admission         = admit activate ;
active_phase      = context channel_state ;
recovery          = fallback? reentry? ;

event             = complete
                  | cancel
                  | release
                  | unregister
                  | process_sigterm
                  | process_sigkill
                  | process_pause
                  | heartbeat_off
                  | heartbeat_on
                  | setpoint_off
                  | setpoint_on
                  | fallback
                  | reentry ;

context           = hover | straight | turn | descent ;
channel_state     = (liveness, setpoint, registration, process_state) ;
process_state     = running | paused | terminated ;
```

`A -> B -> A` and `A -> B -> Fallback -> A` are derived sequences, not special
commands. Every event contains an offset and optional duration; state-conditioned
events additionally contain a bounded predicate.

## Route and event semantics

Routes are allowlisted symbolic IDs: `internal_takeoff`, `internal_hold`,
`internal_rtl`, `internal_land`, `legacy_offboard`, and
`dynamic_external_mode`. An executor adapter resolves the symbol. A case cannot
provide an integer nav state or command payload.

- `admit` requests the mechanism's supported admission lifecycle.
- `activate` selects the external route after admission prerequisites.
- `complete` uses the route's completion primitive.
- `cancel` uses the supported task-cancel primitive.
- `release` stops Offboard through its supported release path.
- `unregister` is valid only for a mechanism with registration lifecycle.
- `process_sigterm`, `process_sigkill`, and `process_pause` target only the
  allowlisted companion producer process created for the case.
- heartbeat and setpoint events toggle their independent observation channels.
- `fallback` requests or awaits an allowlisted internal fallback.
- `reentry` requires a previously active route and a supported fresh lifecycle.

Unsupported surface similarity is rejected. In particular, Offboard release is
not relabeled as dynamic-mode unregister.

## Semantic constraints

The validator enforces all of the following before execution:

1. `activate` follows `admit` when the route requires admission.
2. `unregister` is legal only for `dynamic_external_mode`.
3. No event occurs after terminal process termination except fallback/reentry
   observation.
4. `process_pause` has a bounded duration and an implicit resume.
5. `heartbeat_on` follows a prior `heartbeat_off`; the same rule applies to
   setpoints.
6. Re-entry cannot occur without an earlier exit/fallback.
7. Event offsets are monotonically nondecreasing and within the run duration.
8. At most one process fault is active at a time in v0.
9. The fallback route is internal Hold, RTL, or Land and must be supported by the
   selected transition class.
10. Initial-state constraints must be satisfiable inside the safety envelope.

## Mutation operators

Temporal mutation shifts an event offset, heartbeat/setpoint skew, fault duration,
or repeated-transition interval. It clamps to the envelope and re-sorts only when
the semantic dependency graph permits.

State-conditioned mutation replaces an absolute trigger with a predicate over
speed, descent rate, turn rate, or mission phase. The executor waits only for the
bounded predicate timeout; failure to reach it is `INVALID_SETUP`, not SUT pass or
violation.

Sequence mutation inserts, deletes, repeats, or swaps events and creates bounded
`A -> B -> A` or `A -> B -> Fallback -> A` sequences. The result is discarded as
`INVALID_INPUT` if semantic validation fails.

Channel mutation independently toggles liveness, setpoint, registration, or
process state. Context mutation adjusts speed, turn, descent, and wind inside the
locked envelope.

## Locked safety envelope

```text
vehicle: x500 SITL
world: default
horizontal speed: 0.0 .. 2.0 m/s
descent rate: 0.0 .. 0.5 m/s
turn rate magnitude: 0.0 .. 0.35 rad/s
wind speed: 0.0 .. 2.0 m/s
minimum commanded altitude: 2.0 m AGL
event offset: 0.0 .. 12.0 s
fault duration: 0.1 .. 3.0 s
repeated-transition interval: 1.0 .. 8.0 s
maximum transition events: 12
maximum repetitions per case: 3
maximum evaluation duration: 150 s
```

Values are inclusive. Mutators clamp numeric values, but semantic violations are
rejected rather than silently rewritten. The grammar contains no kill switch,
actuator command, raw message, PX4 parameter mutation, filesystem path, or shell
token.

## Minimization order

The minimizer uses this deterministic order: delete unrelated faults, delete
unrelated transitions, shorten the event sequence, shrink timing toward the
nearest preceding dependency, shrink context amplitudes toward hover, then reduce
repetition. Each candidate must remain schema-valid and reproduce the same target
clause before it replaces the current minimum.
