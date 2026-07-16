# P0 official handoff baseline report

Run date: 2026-07-16. Gate status: **PASS (10/10)**. These runs use PX4
`4ae21a5e569d3d89c2f6366688cbacb3e93437c9`, px4_msgs
`18ecff03041c6f8d8a0012fbc63af0b23dd60af1`, and px4-ros2-interface-lib
`c3e410f035806e8c56246708432ded09c976434b` with the observation-only patch.

## Results

| Scenario | Run ID | Normal-flow result | nav_state sequence | Trace events | Producer / PX4 consume events | Maximum observed message age | Final writer |
|---|---|---|---|---:|---:|---:|---|
| P0-A Offboard | `p0a_offboard_20260716` | PASS; released, RTL landed, disarmed | `4 → 17 → 14 → 4 → 5 → 4` | 2,231 | 183 / 387 | 6.597 ms | `control_allocator` |
| P0-B Dynamic External Mode | `p0b_external_mode_20260716` | PASS; registered as 23, completed once, deactivated, RTL landed, disarmed | `4 → 17 → 23 → 5 → 23` | 2,188 | 8 / 404 | 8.000 ms | `control_allocator` |
| P0-C Mode Executor | `p0c_mode_executor_20260716` | PASS; all executor callbacks through Wait Until Disarmed returned Success | `4 → 23 → 17 → 23 → 5 → 23` | 2,005 | 8 / 382 | 8.000 ms | `control_allocator` |

The lower producer count for P0-B/C reflects structured lifecycle/setpoint
logging at 1 Hz; PX4 consumption is instrumented at the controller update
rate. In all runs the allocator-input writer was `mc_rate_control` and the
final actuator-output writer was `control_allocator`.

P0-C recorded successful results for ready-to-arm, arm, takeoff, external-mode
completion, RTL completion, and Wait Until Disarmed. P0-B recorded exactly one
mode-completion event after three seconds of hover and five seconds of a
0.5 m/s straight-line command.

## What this establishes

- The locked Family A environment can execute normal Internal↔Offboard and
  Internal↔registered External Mode handoffs.
- Producer-side publication and PX4-side consumption are distinct evidence
  streams in the canonical trace.
- The minimal PX4 instrumentation identifies controller consumption,
  allocator-input writer, and actuator-output writer without changing a
  control decision.
- The Mode Executor can sequence the documented Takeoff → Custom Mode → RTL →
  disarm flow on the locked revisions.

## Limits and observed residue

This is a baseline, not a complete correctness verdict. ROS node timestamps
and ULog timestamps remain separate domains; their individual ordering is
valid, but exact cross-domain overlap/gap requires the documented clock bridge.
The runs do not inject loss or contention and therefore do not establish
failure recovery.

After P0-B/C disarmed, `vehicle_status.nav_state` returned to the still
registered external mode ID 23. The aircraft was disarmed and the RTL callback
had succeeded, but this selected-mode residue means P0 must not be cited as
proof of clean re-entry or complete route restoration. It is a concrete target
for later oracle/probe work, outside this phase.

Compact traces and summaries are under `data/processed/p0/`; raw ULogs and
process logs remain ignored under `runs/p0/`.
