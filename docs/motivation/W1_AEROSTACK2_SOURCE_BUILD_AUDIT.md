# W1 Aerostack2 source, build, and interface audit

## Scope and locked identity

This W1-A audit is a bounded SITL study for flight-safety validation, software
reliability, runtime consistency, lifecycle transition, route conformance, and
trace acquisition. It inspected public ROS 2 and PX4 interfaces and
observation-only instrumentation. No formal runtime attempt occurred during
the audit.

The primary workload is Aerostack2 commit
`a8e7318b8d1d7c5adc580e8a16374357773bc11a`. The actual PX4 platform plugin is
`as2_platform_pixhawk` commit
`482563ba979baea965df918995c141a362e26637`, and the simulation project is
`project_px4_vision` commit
`22d945c956ae234839b3c48555ab2c1ba40eaee3`. The flight stack is PX4 commit
`4ae21a5e569d3d89c2f6366688cbacb3e93437c9` with `px4_msgs` commit
`18ecff03041c6f8d8a0012fbc63af0b23dd60af1`. Complete environment and artifact
identity is in `experiments/motivation/w1_workload/source_lock.yaml`.

## Build result

Four non-formal build diagnostics were retained under the ignored raw W1 path.
The first found removed `px4_msgs` observation aliases in the fixed platform
plugin. A minimal compatibility patch removes those aliases and maps the
current GPS and battery observation fields without changing task, route,
setpoint, PX4 mode, fallback, lifecycle, controller, or writer behavior. The
third diagnostic found an undeclared host dependency on `mocap4r2_msgs`; its
official source commit is now locked. The fourth diagnostic built the ten
required packages successfully. These diagnostics do not enter a runtime
denominator and are enumerated in `compatibility_amendment_001.yaml`.

## Public platform interfaces

The platform exposes `set_arming_state`, `set_offboard_mode`,
`set_platform_control_mode`, `platform_takeoff`, `platform_land`, and
`platform/state_machine_event`, and publishes `platform/info`. Its alert input
is the global `alert_event` channel. The workload mission uses the normal arm
and Offboard requests, while internal PX4 takeoff and explicit aircraft Land
remain public PX4 vehicle commands.

The plugin implements arm and disarm with
`VEHICLE_CMD_COMPONENT_ARM_DISARM`. It requests Offboard with
`VEHICLE_CMD_DO_SET_MODE` parameters 1 and 6 after publishing the pre-roll
setpoint stream. The exact plugin does not override Aerostack2's default
platform takeoff or Land implementation, so those two platform services return
failure. Its emergency hover hook reports that stop is not implemented, and
its motor-stop path is outside W1. W1 therefore does not use either path.

The AS2 `platform/info` armed and Offboard flags are synchronized service state;
PX4 `vehicle_status.nav_state`, ULog, and the route trace are the independent
mode evidence. A service result alone is not accepted as route conformance.

## Actions, cancel, completion, and hover

Go-to and follow-path are standard ROS 2 actions. Their servers expose goal
acceptance, feedback, result, and cancellation. Both require FLYING platform
state and current localization. The W1 mission driver must retain the action
goal UUID, request timestamp, feedback, result, cancellation request, and
cancellation acknowledgement.

The position implementations publish `motion_reference/pose` and
`motion_reference/twist` using SensorDataQoS. A successful go-to leaves the
last position reference. Follow-path cancellation deactivates the action; its
non-success execution end then publishes a hover reference. This creates a
real cancel-to-hover lifecycle edge. It does not by itself prove a PX4 route
replacement.

The alert channel defines emergency-hover and aircraft emergency-land
notifications, but they are not part of the low-risk W1 mission. The normal
terminal edge is an explicit aircraft Land request followed by observed landing
and disarm.

## Producer, setpoint, controller, and writer audit

Go-to and follow-path have different upstream behavior-node publishers but use
the same motion-reference topic types and the same position-level interface.
The locked project selects the PID speed controller. The stable
`as2_motion_controller` consumes the position reference and publishes a speed
command. The stable `as2_platform_pixhawk` plugin converts that command to the
PX4 velocity fields of `TrajectorySetpoint` and publishes
`OffboardControlMode` plus `TrajectorySetpoint` at its configured command
frequency. Thus the source audit predicts no final PX4 producer, setpoint
level, controller graph, allocator input, or writer change across go-to,
follow-path, and cancel-to-hover. Runtime evidence, not this prediction, makes
the final classification.

Internal takeoff to Offboard is an expected route replacement: PX4 nav state
and the authority-bearing setpoint route change. Offboard to aircraft Land is
also an expected route replacement. Go-to to follow-path and cancel to hover
remain expected task-only transitions unless route identity, PX4 mode, final
producer/session, controller graph, or writer changes at runtime.

## Native Adapter Gate

The source audit found a workload-specific action lifecycle and timing context,
but no Canonical Adapter gap in PX4 route ownership, final producer/session,
controller graph, writer, cancel fallback, or completion semantics. A separate
Native Adapter would duplicate the same public actions and stable PX4 Offboard
writer, while adding a medium integration burden and no bounded new semantic
claim.

The gate decision is therefore:

- `native_adapter_adds_new_semantics: false`
- `estimated_integration_cost: MEDIUM`
- `native_spike_authorized: false`
- `decision: NOT_APPLICABLE_NO_NEW_ROUTE_OR_LIFECYCLE_SEMANTICS`

W1-E is not authorized. This source decision does not replace source trace
acquisition; W1-B must still test the predicted route and task classifications
at runtime.
