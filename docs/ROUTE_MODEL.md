# Runtime route model

## Runtime Route Instance

A Runtime Route Instance identifies the control path currently capable of
producing a flight-critical actuator effect. Its stable identity is:

```text
(route, route_epoch, producer_session, registration_id, activation_id,
 controller_id, allocator_id, writer_id, lifecycle_owner, executor_owner)
```

`route_epoch` changes whenever PX4 changes authority-relevant route state.
Producer/session identity distinguishes a restarted producer from its
predecessor. Registration and activation identities distinguish allocation of
an external slot from use of that slot. Controller, allocator, and writer
fields form the downstream lineage. Lifecycle and executor fields identify the
owner responsible for completion, unregistration, and successor selection.

Every command-consumption and downstream effect event additionally carries
`command_subject_ns`: the subject time of the state or command being consumed,
not the time a log record was emitted. It is dynamic evidence associated with
the stable route instance rather than a stable identity field, because one
active instance normally consumes many successively newer commands. The
Freshness and Lineage contract evaluates that subject time across the complete
target-authority window.

## Transition interval

The interval begins at `transition_requested`. It closes only after a target
activation and a complete target path have been observed. A complete path has
activation, command consumption, controller output, allocator output, and
actuator write events with one consistent stable Runtime Route Instance
identity. Each effect event must also contain a valid command subject time.

Revocation is timely when source effects stop by the configured deadline and
no source effect appears after target installation. Exclusivity requires that
source and target writers do not overlap after installation. Continuity
requires that the actuator-effect sequence has no observation gap exceeding
the configured bound.

## Route names

The schema uses these stable names:

- `px4_internal`
- `legacy_offboard`
- `dynamic_external_mode`
- `mode_executor`
- `internal_hold`
- `internal_rtl`
- `internal_land`
- `internal_recovery`

Declared mode remains an observation field, but it is not part of the route
identity proof by itself.
