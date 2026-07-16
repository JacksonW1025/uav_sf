# M2 External Mode registration importance

## Conclusion

Dynamic External Mode is a distinct test subject because it adds an explicit,
distributed lifecycle to the route. The lifecycle is observable at several
control-plane points, while the official implementation does not prove the
corresponding complete data-plane route at those points.

## 1. Explicit lifecycle

The locked API exposes discovery/compatibility, registration request/reply,
assigned mode/executor/arming-check IDs, setpoint-type admission, recurring
health/arming replies, nav-state-based activation, periodic setpoint update,
completion, deactivation, explicit unregistration, unresponsive detection, and
fallback selection. Executors add ownership, in-charge state, mode scheduling,
completion callbacks, failsafe deferral, and deactivation reasons.

## 2. Difference from Offboard

Offboard is maintained by a continuous proof-of-life stream and commander
loss/fallback parameters. It has no component registry or assigned producer
identity. Dynamic External Mode first registers capabilities and requirements,
receives an external nav-state ID, and participates in periodic arming checks;
activation later follows vehicle status. The two mechanisms can use the same
trajectory setpoint topic, but their control-plane contracts differ.

## 3. Registration versus activation

`Registration::doRegister` ends when PX4 returns successful IDs. `ModeBase`
activates only when `VehicleStatus.nav_state == id()` and its armed/disarmed
policy permits activation. Registration therefore means eligible/installed in
the control plane; activation means selected. Neither alone proves a fresh
setpoint was consumed or that the intended actuator writer is active.

## 4. Route meaning of mode replacement

Replacement maps an internal mode request to a registered external nav state
and substitutes the external mode requirements. This preserves the user's
semantic request (for example RTL or Descend) while changing producer,
setpoint path, controller configuration, and failure boundary. A displayed
internal mode can therefore conceal an external runtime route; route evidence
must include the assigned ID and data path.

## 5. Node loss and fallback selection

Missing arming-check replies eventually mark the registered mode unresponsive,
which makes it unable to run and enters commander/failsafe selection. Graceful
shutdown publishes unregistration; removing an active mode selects Hold, while
a failed replacement can return to the internal replaced mode according to
commander state and failsafe policy. Executor deactivation reports whether a
failsafe interrupted its schedule.

Heartbeat and setpoint loss are separate. A node may answer arming checks while
its setpoint callback is stalled, or publish setpoints while its lifecycle
reply fails. Both channels must be traced.

## 6. Can current implementation prove complete restoration?

No. The implementation and official integration tests prove selected nav
states, lifecycle callbacks, some fallback selections, setpoint update counts,
landing, and disarming. They do not assert old producer revocation, target
module installation, allocator-input writer, final actuator writer, forbidden
overlap/gap, or absence of re-entry residue. Those are the P-1/M4 gaps addressed
by the route trace and minimal PX4 instrumentation.

## 7. Why test it independently?

Registration, health polling, setpoint admission, activation, executor
scheduling, replacement, and fallback are asynchronous and cross the ROS/DDS,
commander, controller, allocator, and actuator layers. Each layer can reach a
locally consistent state while the full route is incomplete. The explicit
lifecycle creates both valuable observability and failure windows not present
in ordinary Offboard mode.

## 8. Shared Family A / Family B facility

The locked `mc_nn_control` and `mc_raptor` modules publish the same
`register_ext_component_request`, receive assigned mode and arming-check IDs,
reply to `arming_check_request`, and unregister through the same commander
facility. That is the only current cross-family claim. Their setpoint and
actuator paths remain Family B-specific and require new validation before use.
