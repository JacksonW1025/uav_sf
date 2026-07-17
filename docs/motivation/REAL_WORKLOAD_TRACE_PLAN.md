# Real workload trace acquisition plan

## Primary trace: Aerostack2

Pin Aerostack2 at `a8e7318b8d1d7c5adc580e8a16374357773bc11a`, its PX4 platform plugin and simulation project dependencies, the repository PX4/px4_msgs/interface-library lock, simulator world/model hashes, and ROS package snapshot. Do not use a floating Docker tag as provenance.

Run one low-risk mission in SITL:

```text
internal/ground → arm → internal takeoff → Aerostack2 Offboard
→ go-to → follow-path → cancel to hover
→ explicit aircraft Land → disarm
```

Acquire ROS events with a sidecar recorder rather than patching Aerostack2 behavior code. Record service/action request IDs, results, cancellation timestamps, alert events, motion-reference topic and finite components, platform status, ROS clock, and bag metadata/hash. In parallel, record the canonical PX4 trace, RouteObservability profile, ULog, dependency lock, parameters, and clock-bridge segments.

Route classification is performed after acquisition:

- internal → Offboard and Offboard → aircraft Land are expected route replacements;
- go-to → follow-path and cancel → hover remain task transitions unless PX4 mode, producer identity, controller graph, or final writer actually changes;
- missing clock bridge, sequence gaps, or an unpinned platform plugin yields `UNKNOWN`.

## Deterministic replay

Create a compact manifest containing source artifact hashes, topic/type hashes, QoS, start/end timestamps, clock-bridge validity intervals, and the expected state-machine edges. Replay the bag into a trace-only adapter first; do not command SITL during initial replay validation. A later command replay must retain the original low speed/altitude limits and require an explicit test-environment gate.

## Backup trace: MRS

Before installation, pin exact commits for `mrs_uav_core`, `mrs_uav_px4_api`, the selected simulator, and the example mission. Then map MRS tracker/controller and safety events to the canonical schema without treating internal controller switches as PX4 route replacements. Prefer the documented one-drone simulator and a minimal takeoff/hover/land task.

## Exclusions

This plan does not integrate a large stack in Phase A.1, execute kill-switch/emergency motor stop, run high-speed KR missions, or begin random/fuzz testing.
