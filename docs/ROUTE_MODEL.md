# Runtime route and semantic-state model

The narrative source is [NEW_NARRATIVE_v8.md](NEW_NARRATIVE_v8.md). This file
defines the model used by collection, Oracles, and the target generator.

## Runtime Route Instance

A Runtime Route Instance identifies one distinguishable control path capable
of producing a flight-critical actuator effect. Its stable identity is:

```text
(route, route_epoch, producer_session, registration_id, activation_id,
 controller_id, allocator_id, writer_id, lifecycle_owner, executor_owner)
```

- `route_epoch` changes when authority-relevant route state changes.
- `producer_session` distinguishes a restarted producer from its predecessor.
- registration and activation identities distinguish allocation from use.
- controller, allocator, and writer form the downstream command lineage.
- lifecycle and executor owners identify responsibility for completion,
  unregistration, and successor selection.

Every command-consumption and downstream-effect event additionally carries
`command_subject_ns`, the subject time of the consumed command or state. It is
dynamic freshness evidence, not part of stable route identity.

## Transition interval

A transition begins at `transition_requested`. It closes only after target
activation and a complete target path have been observed. A complete path has
activation, command consumption, controller output, allocator output, and
actuator write events with one consistent Runtime Route Instance identity.

The contracts distinguish:

- source revocation;
- target installation;
- writer exclusivity;
- actuator-effect continuity;
- command freshness and lineage;
- completion and successor progression; and
- planned-failure observation and safe-fallback installation.

Declared mode is an observation field. It is never sufficient route-identity
or transition-completion evidence by itself.

## Stable route names

- `px4_internal`
- `legacy_offboard`
- `dynamic_external_mode`
- `mode_executor`
- `internal_hold`
- `internal_rtl`
- `internal_land`
- `internal_recovery`

## Target generator state

The final semantic state contains:

1. route identity, family, and epoch;
2. authority owner and command lineage;
3. registration, activation, execution, completion, replacement, fallback,
   and re-entry phase;
4. health and command-freshness state;
5. successor request, installation, and ownership progress;
6. coarse motion or mission context; and
7. bounded action history for the current sequence.

Raw telemetry and instrumented PX4 events are evidence from which this state
is derived. They are not the paper-level state abstraction. The primary method
is grey-box and must include reduced-observation replay to quantify dependence
on custom instrumentation.

## State transitions and coverage

The target feedback unit is a semantic edge:

```text
(semantic state, action, timing bucket) -> next semantic state
```

Coverage separately records visited states, semantic edges, lifecycle phases,
and contract boundaries. Repeated visits remain counts for reporting but do
not create new coverage.

The current executable prototype observes `route_active` and
`motion_entered`, selects one bounded action time, and feeds back timing-bin
coverage. It does not implement the complete state above.

## Result semantics

Evidence admission precedes all contract results. An inadmissible trace is
`INCONCLUSIVE` even if an individual clause appears favorable.

Finding interpretation is layered:

1. research-contract exposure;
2. reproducible cross-layer contract violation;
3. source-grounded PX4 defect; and
4. safety-relevant finding with a reproducible task or physical consequence.

These levels must remain separate in coverage, benchmark, and defect counts.
