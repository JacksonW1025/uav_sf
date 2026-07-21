# R1 Session Semantic Audit

Date: 2026-07-20

Selected R1-C semantic: `ModeCompleted`

Contract classification: `B. implied ownership/progression contract`

## Locked source identity

This audit is limited to the following exact local revisions:

- study repository starting checkpoint:
  `d78a206080a033f20fbd66fdb940c2ff8b1040d2`;
- PX4-Autopilot: `4ae21a5e569d3d89c2f6366688cbacb3e93437c9`;
- `px4_msgs`: `18ecff03041c6f8d8a0012fbc63af0b23dd60af1`;
- `px4-ros2-interface-lib`:
  `c3e410f035806e8c56246708432ded09c976434b`.

The local PX4 checkout also contains the repository's previously frozen
observation-only route patch. Its diff was checked: it adds lifecycle/route
observations but does not change the registration, setpoint-configuration,
override, completion, or ordinary-setpoint matching rules described here.

Audited message definitions are `RegisterExtComponentRequest.msg`,
`RegisterExtComponentReply.msg`, `SetpointConfig.msg`,
`SetpointConfigReply.msg`, `ConfigOverrides.msg`, `ModeCompleted.msg`, and
`TrajectorySetpoint.msg` at the locked `px4_msgs` revision. Audited library
symbols are `Registration::doRegister`,
`ModeBase::checkSetpointCompatibilityAndRequirements`,
`ModeBase::activateSetpointType`, `ModeBase::completed`,
`ConfigOverrides::setup/update`,
`ModeExecutorBase::ScheduledMode::{activate,ScheduledMode}`, and
`TrajectorySetpointType::update`. PX4-side anchors are
`ModeManagement::{checkNewRegistrations,checkConfigControlSetpointUpdates,
checkConfigOverrides}` and the locked `dds_topics.yaml` topic map.

## Identity comparison

| Semantic | Fields relevant to identity | Receiver correlation/matching | Instance or generation identity | R1-C disposition |
|---|---|---|---|---|
| Registration request/reply | Request has random `uint64 request_id`, name, API version, and requested component roles; reply repeats `request_id` and name and assigns arming-check, mode, and executor IDs | The library requires both name equality and exact request/reply `request_id`; PX4 copies both into the reply | Strong per-request correlation is present. Assigned IDs are reusable slots, not an activation-generation token carried by later messages | Excluded as the delayed semantic; retained as the old/new identity baseline |
| Setpoint configuration | `timestamp`, setpoint `type`, numeric `source_id` (`nav_state`), `should_apply`, and `timeout_ms`; reply repeats `type` and `source_id` | The library accepts a reply matching current mode ID and type; PX4 looks up the current valid mode slot by `source_id` | No request ID, registration instance, producer session, or activation generation | Excluded because it changes controller configuration and would mix session isolation with configuration-policy effects |
| Configuration override | Override values plus `source_type` and numeric `source_id` | PX4 writes the request into the currently valid mode/executor slot; the library confirms by comparing all fields except timestamp | No registration request ID, producer session, or activation generation | Excluded because it changes failsafe/auto-home/auto-disarm policy and is not the narrow lifecycle progression semantic |
| Completion | `timestamp`, `result`, and `nav_state` | `ModeBase::completed` publishes the assigned mode ID. `ScheduledMode` accepts the message when its wait is active and `msg.nav_state == _mode_id`, then moves the callback, resets the wait, and invokes the callback | No component name, registration request ID, arming-check ID, executor ID, producer identity, session identity, activation ID, or generation | Selected |
| Ordinary Trajectory setpoint | `timestamp`, position, velocity, acceleration, jerk, yaw, and yaw rate | All publishers use the shared trajectory-setpoint interface; PX4 consumes the ordinary topic under the current configured route | No mode, executor, registration, producer-session, activation, or generation identity | Excluded because provenance is absent on wire and retained-input behavior was already bounded by frozen N1 |

## Why completion was selected

`ModeCompleted` is the only audited candidate whose ordinary successful
handling directly advances a Mode Executor lifecycle. The message definition
says it is published by an active mode, and the executor creates a completion
wait for a scheduled mode. These establish an implied lifecycle-owner and
progression expectation. The receiver, however, can distinguish only an
active wait and a matching numeric `nav_state`. If an unregistered mode slot is
later reused, the wire contract supplies no old/new generation discriminator.

This makes completion the narrowest source-backed R1-C semantic: it can test
session ownership at the lifecycle boundary without adding a second
setpoint-freshness study, changing PX4 configuration policy, or writing any
internal state.

Registration was not selected because its explicit random request ID and name
already provide request/reply correlation and because registration itself is
required to establish the rollover. Setpoint configuration and overrides were
not selected because they alter controller or safety-policy state and would
confound the lifecycle question. Ordinary setpoints were not selected because
they carry no producer identity and because delayed/retained Trajectory input
belongs to the completed and frozen N1 scope.

## Public lifecycle sequence

The condition can arise through the following ordinary local sequence:

```text
earlier local component registers mode + executor
  → earlier mode activates and its completion value is associated with that
    producer session by the harness
  → earlier component legally unregisters (R1-A/R1-C) or stops and PX4
    installs configured fallback (R1-B)
  → new local component registers and receives current mode/executor slots
  → new mode activates and its executor arms a completion wait
  → the single held ModeCompleted value is delivered through
    /fmu/in/mode_completed
  → observe relay, callback/progression, successor request/installation,
    route lineage, and cleanup
```

The registered R1-C statement is:

> A completion event associated by the test harness with the earlier local
> producer session is delivered through the normal local SITL interface after
> a new registered/activated session exists. The study observes whether the new
> lifecycle progresses and whether the API can distinguish the two sessions.

The study calls this the **completion-session isolation check**.

## Old/new evidence rule

The public `ModeCompleted` value cannot itself distinguish the two sessions.
The test harness therefore keeps independent provenance evidence:

- the registration request ID and correlated public reply for each component;
- a harness-generated registration-instance ID logged by each local process;
- distinct old/new producer-session IDs;
- an activation key formed from producer session, registration instance, and
  per-process activation count;
- assigned mode/executor IDs, explicitly treated as reusable slots;
- source and target PX4 route epochs mapped with a `VALID` clock bridge; and
- the one-time completion release record, PX4 relay observation, new executor
  callback, successor request, successor installation, and complete
  controller/allocator/writer lineage.

Complete identity showing no distinct old/new relation is
`NOT_APPLICABLE`. Missing identity is `UNKNOWN`. A wire event whose generation
cannot be resolved after the required relation exists is `EXPOSURE`. A
`VIOLATION` requires complete causal evidence that an event associated with the
earlier producer progressed the new lifecycle and successor in contradiction
to the implied owner/progression relation. Mere observation or apparent
acceptance is not automatically classified as a defect.

## Limitations and policy ambiguity

The locked public API does not state an explicit registration-generation
guarantee for completion. The active-mode wording and executor scheduling
model imply ownership, while the wire representation uses only a reusable
mode number. R1 therefore classifies the lifecycle contract as implied, not
explicit, and preserves `EXPOSURE` for measurable ambiguity without proved
contradiction.

The harness association establishes experimental provenance; it does not add
an identity field to PX4. The study covers one locked PX4/interface revision,
one vehicle/world, one completion result, and bounded event timing. It cannot
estimate natural frequency, generalize to all transports or vehicles, or
establish physical consequence. The semantic audit freezes only
`ModeCompleted`; adding another delayed semantic requires a future
preregistration.
