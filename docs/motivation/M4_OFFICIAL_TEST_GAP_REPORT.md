# M4 official route-transition test gap

Audit basis: PX4 `4ae21a5e569d3d89c2f6366688cbacb3e93437c9`
and px4-ros2-interface-lib
`c3e410f035806e8c56246708432ded09c976434b`. The matrix contains 15 source- or
assertion-backed rows. `PARTIAL` means the cited assertion/source exercises a
piece of the field, not that the complete route obligation is tested.

## What official tests establish

- `ModeManagementTest` confirms external-mode slots, removal, and name hashes.
- ROS integration tests confirm successful registration, nav-state activation,
  lifecycle callback counts, basic setpoint updates, replacement selection,
  failsafe deactivation, internal Descend selection, landing, and disarming.
- PX4 failsafe unit tests confirm selected actions such as Hold, RTL, Descend,
  Land, termination, takeover, and deferral.
- MAVSDK Offboard tests confirm ordinary position/attitude behavior and landing
  outcomes.
- Official examples encode basic go-to, multiple-mode, replacement, and
  Takeoff → External Mode → RTL → disarm workflows.

Thus there is meaningful coverage of nav-state/mode state, fallback selection,
and basic behavior.

## Missing route obligations

No audited official assertion identifies the concrete ROS producer or final
uORB writer. No test compares producer and consumer freshness at the handoff.
No test proves the old route stopped influencing output, all modules of the
target route were installed, or exactly one valid route controlled the vehicle
through the transition. There is no overlap/gap oracle.

The tests count setpoint updates or observe final nav/land/disarm states, but do
not inspect module-state installation, allocator input identity, actuator
writer, or output continuity. Destruction/unregistration and mode slot reuse
provide only partial re-entry evidence; they do not detect stale subscriptions,
setpoints, controller state, or residue across repeated activation.

Fallback selection is therefore better covered than complete recovery. A
vehicle reaching Descend/Land/disarmed does not prove timely old-route
revocation or the absence of a transient competing writer.

## Consequence for this phase

P0 can reproduce normal official flows, but its purpose is to validate the new
trace, clock, and writer evidence—not to claim a newly discovered bug. Later
oracles must add explicit revocation, installation, overlap/gap, residue, and
complete recovery checks before fault injection or search begins.
