# Aerostack2 Runtime Route Map

Dependency profile: `aerostack2-runtime-trace-spike-humble`; exact commits are
in `config/aerostack2_dependencies.lock.yaml`. This is a narrow PX4/Offboard
acquisition spike, not a general assessment of Aerostack2.

## Control-path map

The Pixhawk platform's `set_offboard_mode` service reaches
`AerialPlatform::setOffboardControl()` and then
`PixhawkPlatform::ownSetOffboardControl(true)`. The platform first publishes ten
body-rate setpoints and then sends `VEHICLE_CMD_DO_SET_MODE` with PX4 custom mode
6. This is only a true route handoff when PX4's data plane independently records
an internal mode to Offboard (`nav_state=14`) transition.

Aerostack2 motion behaviors publish `motion_reference/pose`,
`motion_reference/twist`, or `motion_reference/trajectory`. The platform maps
those references to PX4 trajectory, attitude, or rate setpoints and continually
publishes the matching `OffboardControlMode`. A goal modification, action
cancel, or transition between motion behaviors is therefore an in-route update
when the PX4 mode and route epoch do not change. Names such as “land” or
“cancel” are not treated as route changes without PX4 evidence.

The selected Pixhawk adapter does not implement `ownStopPlatform()` and inherits
the default unsupported `ownLand()`. Its kill-switch path publishes
`ManualControlSwitches.kill_switch=true`; that path is outside this goal's safety
boundary and is never invoked. Safe emergency-land claims therefore require a
separate observed PX4 Land request and are not inferred from an Aerostack2 alert
name.

## Acquisition scenarios

The spike prioritizes:

- A1: platform Offboard request, classified only after a PX4 internal→Offboard
  mode change and target consumption/writer evidence;
- A2: mission completion/controlled exit, classified from the resulting PX4
  mode;
- A3: action cancel while Offboard, expected to be a non-handoff when the route
  epoch remains stable;
- A4: companion process loss, a true handoff only if PX4 leaves Offboard;
- A5: safe Land request only; the kill-switch implementation is prohibited.

`scripts/workloads/aerostack2_trace_adapter.py` merges runtime-monitor events
with the PX4 ULog-derived trace without inventing PX4 state. Its summary labels
`TRUE_ROUTE_HANDOFF` only from `vehicle_status` mode transitions. A behavior
event with no external-route transition is labeled
`NON_HANDOFF_TASK_TRANSITION`.

## Evidence boundary

Source inspection establishes which API calls and topics can request or update
control. Runtime classification additionally requires the retained Aerostack2
event log and the schema-1.2 PX4 data-plane trace. Source names alone never
establish admission, consumption, fallback, or actuator authority.
