# Preregistration

## Aim and boundary

The study asks whether declared mode and terminal flight outcome alone prove
a complete authority handoff, whether Route, Freshness, and Successor Oracles
have independent detection value, whether the Thor loop yields admissible
evidence, and which partial failures and timing boundaries merit later
state-aware exploration. It does not compare search algorithms or claim
complete route-pair coverage.

The target is PX4 SITL, `gz_x500`, headless Gazebo Harmonic, ARM64 AGX Thor.
Pixhawk, hardware-in-the-loop, and real flight are excluded.

## Legal paths and cells

The frozen matrix uses only publicly requested, legally reachable transitions:

- PX4 Internal to Legacy Offboard, then Hold, RTL, or Land;
- PX4 Internal to Dynamic External Mode, then Hold, RTL, or Land;
- executor-owned External Mode through completion to Land and disarm;
- planned producer exit, setpoint-only stall, health loss, and public
  registration-capacity rejection;
- completion-adjacent manual requests in before, near-simultaneous, and after
  buckets;
- repeated Legacy Offboard entry through public Hold or RTL transitions;
- representative trajectory, attitude, and body-rate setpoint paths.

No direct Legacy Offboard to Dynamic External Mode replacement is injected,
because the study does not mutate PX4 internal state to manufacture a route.

## Evidence and decisions

ROS/DDS telemetry and lifecycle sidecars drive independent live safety and
process supervision. PX4 uORB RouteObservability retained in ULog is the
authority for route/controller/allocator/writer/subject lineage. A clock bridge
joins the domains. The Evidence Gate must admit the normalized closed trace
before any Oracle result is interpreted. An incomplete window, sequence gap,
invalid mapping, missing identity, or missing required event is rejected or
inconclusive; absence is never a pass.

`ACCEPTED` means admissible evidence, not Oracle success. Thus a preregistered
Oracle violation consumes the attempt and remains in the formal result.

## Sample and accounting contract

- deterministic normal and successor cells: 5 accepted, cap 10 launches;
- process/health/setpoint fault cells: 8 accepted, cap 16 launches;
- timing and repeated-entry cells: 10 accepted, cap 20 launches.

Every launch is hash-chain registered before container startup and closes as
`ACCEPTED`, `OBSERVABILITY_REJECTED`, `INCONCLUSIVE`,
`ENVIRONMENT_FAILURE`, `CAMPAIGN_CONFIGURATION_FAILURE`,
`FORMAL_SAFETY_STOP`, or `TIMEOUT`. No rejected launch is silently replaced.
A cell at cap without its target is `MEASUREMENT_INSUFFICIENT`.

Qualification seeds and directories are disjoint from the formal namespace.
Formal thresholds and concurrency cannot change after the first formal
registration. The exact machine-readable matrix and environment attestation
complete this preregistration before execution.
