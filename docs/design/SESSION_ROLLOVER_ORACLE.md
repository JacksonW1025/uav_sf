# Session Rollover Oracle

Version: `0.1`. Result schema: `1.0`.

## Purpose and contract

The Session Rollover Oracle evaluates whether a newly registered and activated
local External Mode instance remains isolated from lifecycle state associated
with an earlier local instance. It does not infer a session from a reused
numeric `nav_state` or executor slot.

R1 uses contract classification
`B_IMPLIED_OWNERSHIP_PROGRESSION_CONTRACT`. The public lifecycle model says
that an active mode publishes its completion and an active Mode Executor wait
consumes the matching completion. That establishes an ownership/progression
expectation, but `ModeCompleted` has no registration-instance or activation-
generation field. R1 therefore does not claim an explicit generation
guarantee. A wire-identity ambiguity is an `EXPOSURE`; a `VIOLATION` requires
complete evidence that an event associated with the earlier producer session
changed the new lifecycle or its successor.

## Identity and applicability

The old/new relation is the tuple:

```text
registration request_id and correlated reply
  × harness registration_instance_id
  × producer_session_id
  × activation key (producer session, registration instance, activation count)
```

Assigned mode and executor IDs are observations, not generation identifiers;
PX4 may legally reuse both after unregistration. Missing old identity or new
activation evidence is `UNKNOWN`. Complete evidence showing that the supposed
old and new tuples are not distinct is `NOT_APPLICABLE` because no session
rollover was established.

## Required evidence

The executable joins:

- public registration requests and replies, including `request_id`, assigned
  mode, executor, and arming-check IDs;
- old/new structured component logs carrying registration, activation, and
  producer-session identity;
- old/new active snapshots and a `VALID` ROS-to-PX4 clock bridge with at least
  20 samples covering the complete isolation window;
- source and target route epochs, plus any completion-driven successor epoch;
- completion generation provenance assigned by the local harness, the single
  public-interface release, PX4 relay observation, executor callback, successor
  request, and successor installation;
- controller-consumption, allocator-input, and final-writer lineage carrying
  route epochs; and
- safe Land/Disarm cleanup.

The R1-C semantic is solely `ModeCompleted`. Configuration overrides and
ordinary setpoints remain audit context and are not released in this matrix.

## Clauses

`registration_and_activation_identity` checks complete identities and the
explicit registration request/reply correlation. Numeric slot reuse is
reported but is not itself a failure.

`session_relation` establishes two distinct local producer sessions. A proved
same-session relation makes the scenario `NOT_APPLICABLE`; absent identity is
`UNKNOWN`.

`route_epoch_rollover` requires the new activation to occupy a target epoch
different from the earlier active source epoch.

`lifecycle_owner_rollover` requires the earlier local component to have stopped
or unregistered, the new executor to own the new active mode, and no later
authority-bearing event from the old producer.

`completion_session_isolation` is applicable only to R1-C:

- a new-session completion with complete expected progression is `PASS`;
- an earlier-session completion that is observed but ignored is `PASS`;
- an on-wire event whose old/new provenance cannot be resolved is `EXPOSURE`;
- an earlier-session completion that progresses the new lifecycle, with a
  causally observed successor request and installed successor epoch, is
  `VIOLATION`; and
- missing provenance, release count, relay, successor, or progression evidence
  is `UNKNOWN`.

Thus reception or apparent acceptance alone is never automatically called a
bug.

`successor_progression` records the request and installation needed to prove a
completion-driven lifecycle change. It is `NOT_APPLICABLE` when no completion
progression occurs.

`controller_lineage_isolation` and
`allocator_writer_lineage_isolation` require a complete new-session window and
reject old-epoch influence. Shared module names do not establish old lineage;
the route epoch must match the earlier source epoch.

`cleanup` requires both landed and disarmed evidence.

## Overall result

The result vocabulary is:

- `PASS`: the new session is isolated and every applicable obligation passes;
- `EXPOSURE`: the public completion identity is insufficient in an observed
  ambiguity window, without a proved ownership violation;
- `VIOLATION`: complete evidence contradicts the implied lifecycle ownership
  or an explicit registration/route obligation;
- `UNKNOWN`: any required identity, timing, route, lifecycle, lineage,
  successor, or cleanup evidence is incomplete; and
- `NOT_APPLICABLE`: complete evidence does not establish the required old/new
  session relation.

`UNKNOWN` dominates a provisional finding because incomplete evidence cannot
support a conformance or violation claim. Otherwise `VIOLATION` dominates
`EXPOSURE`, which dominates `PASS`.

## Boundaries

The completion-session isolation check releases one locally held event through
the normal local SITL interface only after the new registered/activated
session and executor wait are observed. The harness never writes PX4
`nav_state`, registration tables, executor state, controller memory, or
failsafe state. Results are bounded to the locked source, binary, vehicle,
world, event order, and timing profile and do not establish occurrence
frequency or physical consequence.
